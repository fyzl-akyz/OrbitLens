"""
ISS & Spacecraft Tracker
Real-time tracking of the International Space Station and astronauts in orbit.
APIs: open-notify.org | wheretheiss.at
"""

import tkinter as tk
from tkinter import ttk, font
import requests
import threading
import time
import math
import os
import sys
import re
import io
from datetime import datetime, timezone
from pathlib import Path

import tkintermapview

# ─── Try to import PIL (Pillow) ───────────────────────────────────────────────
try:
    from PIL import Image, ImageTk, ImageDraw, ImageFilter, ImageEnhance
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ─── Constants ────────────────────────────────────────────────────────────────
MAP_W, MAP_H = 900, 450          # Canvas dimensions for the map
TRAIL_MAX     = 60               # Maximum number of trail dots
REFRESH_MS    = 5000             # Refresh every 5 seconds
ISS_NORAD_ID  = 25544

API_ISS_POS   = "http://api.open-notify.org/iss-now.json"
API_ASTRONAUTS= "http://api.open-notify.org/astros.json"
API_ISS_EXT   = f"https://api.wheretheiss.at/v1/satellites/{ISS_NORAD_ID}"
API_EONET     = "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=10"
API_APOD      = "https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY"



# ─── Colors ───────────────────────────────────────────────────────────────────
C_BG         = "#050b18"
C_PANEL      = "#0d1b2e"
C_PANEL_DARK = "#070f1c"
C_BORDER     = "#1e3a5f"
C_ACCENT     = "#00d4ff"
C_ACCENT2    = "#7b2fff"
C_TEXT       = "#e0f0ff"
C_MUTED      = "#6a8aaa"
C_ISS        = "#00ffaa"
C_TRAIL      = "#00d4ff"
C_WARN       = "#ff6b35"
C_GREEN      = "#39ff14"



class ISSTracker(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🛰️  Live Spacecraft Tracker")
        self.configure(bg=C_BG)
        self.resizable(True, True)
        self.minsize(1020, 660)

        # State
        self.active_sat_name = "ISS (Zarya)"
        self.active_sat_id = ISS_NORAD_ID


        self.trail: list[tuple[float, float]] = []
        self.iss_data: dict = {}
        self.ext_data: dict = {}
        self.astronaut_data: list = []
        self.last_update: str = "—"
        self.fetch_error: str = ""
        self.update_count: int = 0
        self.earth_events: list = []
        self.apod_data: dict = {}
        self.apod_img_data = None
        self.apod_photoimage = None

        self.map_widget = None
        self.sat_marker = None
        self.trail_path = None
        self.terminator_poly = None
        self.sat_icon = None
        self.event_markers = []


        if PIL_AVAILABLE:
            sat_path = Path(__file__).parent / "sat.png"
            if sat_path.exists():
                try:
                    img = Image.open(sat_path).convert("RGBA").resize((48, 48), Image.LANCZOS)
                    self.sat_icon = ImageTk.PhotoImage(img)
                except Exception:
                    pass


        # Build UI
        self._build_ui()

        # Start background fetch loop
        self._schedule_fetch()

        # Center window
        self.update_idletasks()
        w, h = 1100, 700
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────────
        header = tk.Frame(self, bg=C_PANEL_DARK, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header, text="🛰️  LIVE SPACECRAFT TRACKER",
            bg=C_PANEL_DARK, fg=C_ACCENT,
            font=("Consolas", 18, "bold"), pady=10
        ).pack(side="left", padx=20)

        self.lbl_clock = tk.Label(
            header, text="", bg=C_PANEL_DARK, fg=C_MUTED,
            font=("Consolas", 11)
        )
        self.lbl_clock.pack(side="right", padx=20)
        self._tick_clock()

        self.lbl_status = tk.Label(
            header, text="⏳ Connecting…", bg=C_PANEL_DARK, fg=C_WARN,
            font=("Consolas", 10)
        )
        self.lbl_status.pack(side="right", padx=10)

        # ── Main split ────────────────────────────────────────────────────────
        main = tk.Frame(self, bg=C_BG)
        main.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Left: map + bottom bar
        left = tk.Frame(main, bg=C_BG)
        left.pack(side="left", fill="both", expand=True)

        # Right sidebar
        right_wrapper = tk.Frame(main, bg=C_PANEL, width=290)
        right_wrapper.pack(side="right", fill="y", padx=(8, 0))
        right_wrapper.pack_propagate(False)

        self.sidebar_canvas = tk.Canvas(right_wrapper, bg=C_PANEL, highlightthickness=0)
        sidebar_scroll = ttk.Scrollbar(right_wrapper, orient="vertical", command=self.sidebar_canvas.yview)
        
        right = tk.Frame(self.sidebar_canvas, bg=C_PANEL)
        right.bind(
            "<Configure>",
            lambda e: self.sidebar_canvas.configure(scrollregion=self.sidebar_canvas.bbox("all"))
        )
        
        # 275 width to leave space for scrollbar
        self.sidebar_canvas.create_window((0, 0), window=right, anchor="nw", width=275)
        self.sidebar_canvas.configure(yscrollcommand=sidebar_scroll.set)
        
        self.sidebar_canvas.pack(side="left", fill="both", expand=True)
        sidebar_scroll.pack(side="right", fill="y")
        
        # Simple scroll binding (Windows)
        right_wrapper.bind("<Enter>", lambda e: self.sidebar_canvas.bind_all("<MouseWheel>", lambda ev: self.sidebar_canvas.yview_scroll(int(-1*(ev.delta/120)), "units")))
        right_wrapper.bind("<Leave>", lambda e: self.sidebar_canvas.unbind_all("<MouseWheel>"))


        # ── Map widget ────────────────────────────────────────────────────────
        map_frame = tk.Frame(left, bg=C_BORDER, bd=0)
        map_frame.pack(fill="both", expand=True, pady=(8, 4))

        self.map_widget = tkintermapview.TkinterMapView(map_frame, corner_radius=0, bg_color="#05101e")
        self.map_widget.pack(fill="both", expand=True, padx=1, pady=1)
        self.map_widget.set_tile_server("https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}&s=Ga", max_zoom=22)
        self.map_widget.set_zoom(3)
        self.map_widget.set_position(0, 0) # Center of the world

        # Initialize terminator polygon early so it stays at the bottom of the Z-order
        self.terminator_poly = self.map_widget.set_polygon([(0,0), (0,0)], outline_color="", fill_color="#000000", border_width=0)

        # ── ISS Info bar (below map) ───────────────────────────────────────────
        info_row = tk.Frame(left, bg=C_PANEL_DARK, height=80)
        info_row.pack(fill="x", pady=(0, 0))
        info_row.pack_propagate(False)

        self.info_vars = {}
        info_fields = [
            ("LAT",      "Latitude",    "°"),
            ("LON",      "Longitude",   "°"),
            ("ALT",      "Altitude",    "km"),
            ("VEL",      "Velocity",    "km/h"),
            ("VIS",      "Visibility",  ""),
            ("FOOT",     "Footprint",   "km"),
        ]
        for key, label, unit in info_fields:
            col = tk.Frame(info_row, bg=C_PANEL_DARK)
            col.pack(side="left", expand=True, pady=8)
            tk.Label(col, text=label.upper(), bg=C_PANEL_DARK,
                     fg=C_MUTED, font=("Consolas", 8)).pack()
            var = tk.StringVar(value="—")
            self.info_vars[key] = var
            tk.Label(col, textvariable=var, bg=C_PANEL_DARK,
                     fg=C_ACCENT, font=("Consolas", 14, "bold")).pack()
            if unit:
                tk.Label(col, text=unit, bg=C_PANEL_DARK,
                         fg=C_MUTED, font=("Consolas", 8)).pack()

        # ── Right sidebar ─────────────────────────────────────────────────────
        self._build_sidebar(right)


    def _build_sidebar(self, parent):

        # Section: Spacecraft Details
        self._sidebar_section(parent, "📡  SPACECRAFT DETAILS")

        detail_fields = [
            ("Latitude",     "detail_lat"),
            ("Longitude",    "detail_lon"),
            ("Altitude",     "detail_alt"),
            ("Velocity",     "detail_vel"),
            ("Visibility",   "detail_vis"),
            ("Solar Lat",    "detail_solarlat"),
            ("Solar Lon",    "detail_sonarlon"),
            ("Daylight",     "detail_daylight"),
            ("Last Update",  "detail_update"),
        ]
        self.detail_vars = {}
        for label, key in detail_fields:
            row = tk.Frame(parent, bg=C_PANEL)
            row.pack(fill="x", padx=12, pady=1)
            tk.Label(row, text=label + ":", bg=C_PANEL, fg=C_MUTED,
                     font=("Consolas", 9), width=12, anchor="w").pack(side="left")
            var = tk.StringVar(value="—")
            self.detail_vars[key] = var
            tk.Label(row, textvariable=var, bg=C_PANEL, fg=C_TEXT,
                     font=("Consolas", 9, "bold"), anchor="w").pack(side="left", fill="x")

        tk.Frame(parent, bg=C_BORDER, height=1).pack(fill="x", padx=12, pady=8)

        # Section: Crew in Space
        self._sidebar_section(parent, "👨‍🚀  CREW IN SPACE")

        self.crew_frame = tk.Frame(parent, bg=C_PANEL)
        self.crew_frame.pack(fill="x", padx=8, pady=4)

        # Section: Other Spacecraft
        # Section: NASA Earth Events
        tk.Frame(parent, bg=C_BORDER, height=1).pack(fill="x", padx=12, pady=8)
        self._sidebar_section(parent, "🌍  NASA EARTH EVENTS")
        self.events_frame = tk.Frame(parent, bg=C_PANEL)
        self.events_frame.pack(fill="x", padx=8, pady=4)

        # Section: Astronomy Picture
        tk.Frame(parent, bg=C_BORDER, height=1).pack(fill="x", padx=12, pady=8)
        self._sidebar_section(parent, "🌌  ASTRONOMY PICTURE")
        self.apod_frame = tk.Frame(parent, bg=C_PANEL)
        self.apod_frame.pack(fill="x", padx=8, pady=4)

        # Section: Other Spacecraft

        self.other_frame = tk.Frame(parent, bg=C_PANEL)
        self.other_frame.pack(fill="x", padx=8, pady=4)

        # Refresh button
        tk.Frame(parent, bg=C_BORDER, height=1).pack(fill="x", padx=12, pady=8)
        btn = tk.Button(
            parent, text="⟳  REFRESH NOW",
            bg=C_ACCENT2, fg="white",
            activebackground="#5a1fd1",
            font=("Consolas", 10, "bold"),
            relief="flat", cursor="hand2",
            command=self._force_refresh
        )
        btn.pack(fill="x", padx=16, pady=(0, 12))

        # Attribution
        tk.Label(
            parent,
            text="Data: open-notify.org | wheretheiss.at",
            bg=C_PANEL, fg=C_MUTED,
            font=("Consolas", 7), wraplength=240
        ).pack(pady=(0, 8))

    def _sidebar_section(self, parent, title: str):
        tk.Label(
            parent, text=title,
            bg=C_PANEL, fg=C_ACCENT2,
            font=("Consolas", 10, "bold"),
            anchor="w"
        ).pack(fill="x", padx=12, pady=(10, 2))

    # ── Clock ─────────────────────────────────────────────────────────────────
    def _tick_clock(self):
        now = datetime.now(timezone.utc).strftime("UTC  %Y-%m-%d  %H:%M:%S")
        self.lbl_clock.config(text=now)
        self.after(1000, self._tick_clock)

    # ── Fetch logic ───────────────────────────────────────────────────────────
    def _schedule_fetch(self):
        t = threading.Thread(target=self._fetch_all, daemon=True)
        t.start()

    def _force_refresh(self):
        self.lbl_status.config(text="⏳ Refreshing…", fg=C_WARN)
        self._schedule_fetch()

    def _fetch_all(self):
        errors = []

        # 1) Astronauts (Always fetch, it's global)
        try:
            r = requests.get(API_ASTRONAUTS, timeout=8)
            r.raise_for_status()
            self.astronaut_data = r.json().get("people", [])
        except Exception as e:
            errors.append(f"Astronauts: {e}")

        # 2) Position Data
        # Basic ISS position
        try:
            r = requests.get(API_ISS_POS, timeout=8)
            r.raise_for_status()
            d = r.json()
            self.iss_data = d["iss_position"]
        except Exception as e:
            errors.append(f"ISS-pos: {e}")

        # Extended ISS data
        try:
            r = requests.get(API_ISS_EXT, timeout=8)
            r.raise_for_status()
            self.ext_data = r.json()
        except Exception as e:
            errors.append(f"ISS-ext: {e}")

        # 3) NASA Earth Events (EONET)

        try:
            r = requests.get(API_EONET, timeout=8)
            r.raise_for_status()
            self.earth_events = r.json().get("events", [])
        except Exception as e:
            errors.append(f"NASA-EONET: {e}")

        # 4) NASA Astronomy Picture of the Day (APOD)
        # Only fetch once per hour or if empty
        if not self.apod_data or self.update_count % 12 == 0:
            try:
                r = requests.get(API_APOD, timeout=8)
                r.raise_for_status()
                data = r.json()
                self.apod_data = data
                if data.get("media_type") == "image" and data.get("url"):
                    img_r = requests.get(data["url"], timeout=10)
                    img_r.raise_for_status()
                    self.apod_img_data = img_r.content
            except Exception as e:
                errors.append(f"NASA-APOD: {e}")

        self.fetch_error = "; ".join(errors)

        self.last_update = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        self.update_count += 1

        # Update trail
        if self.iss_data:
            lat = float(self.iss_data["latitude"])
            lon = float(self.iss_data["longitude"])
            self.trail.append((lat, lon))
            if len(self.trail) > TRAIL_MAX:
                self.trail.pop(0)

        # Schedule UI update on main thread
        self.after(0, self._update_ui)
        # Schedule next fetch
        self.after(REFRESH_MS, self._schedule_fetch)

    # ── UI update ─────────────────────────────────────────────────────────────
    def _update_ui(self):
        if self.fetch_error and not self.iss_data:
            self.lbl_status.config(text=f"⚠  {self.fetch_error[:60]}", fg=C_WARN)
        else:
            self.lbl_status.config(
                text=f"✓  Live  •  #{self.update_count}  •  {self.last_update}",
                fg=C_GREEN
            )

        # Info bar
        lat = float(self.iss_data.get("latitude",  0))
        lon = float(self.iss_data.get("longitude", 0))
        alt  = self.ext_data.get("altitude",   0)
        vel  = self.ext_data.get("velocity",   0)
        vis  = self.ext_data.get("visibility", "—")
        foot = self.ext_data.get("footprint",  0)

        self.info_vars["LAT"].set(f"{lat:+.4f}")
        self.info_vars["LON"].set(f"{lon:+.4f}")
        self.info_vars["ALT"].set(f"{alt:.1f}"  if alt  else "—")
        self.info_vars["VEL"].set(f"{vel:.0f}"  if vel  else "—")
        self.info_vars["VIS"].set(vis.capitalize() if vis else "—")
        self.info_vars["FOOT"].set(f"{foot:.0f}" if foot else "—")

        # Sidebar details
        self.detail_vars["detail_lat"].set(f"{lat:+.6f}°")
        self.detail_vars["detail_lon"].set(f"{lon:+.6f}°")
        self.detail_vars["detail_alt"].set(f"{alt:.2f} km"  if alt  else "—")
        self.detail_vars["detail_vel"].set(f"{vel:.2f} km/h" if vel else "—")
        self.detail_vars["detail_vis"].set(vis.capitalize() if vis else "—")
        sl  = self.ext_data.get("solar_lat", None)
        slo = self.ext_data.get("solar_lon", None)
        self.detail_vars["detail_solarlat"].set(f"{sl:.2f}°"  if sl  is not None else "—")
        self.detail_vars["detail_sonarlon"].set(f"{slo:.2f}°" if slo is not None else "—")
        daylight = "☀ Day" if vis == "daylight" else ("🌑 Night" if vis and vis != "—" else "—")
        self.detail_vars["detail_daylight"].set(daylight)
        self.detail_vars["detail_update"].set(self.last_update)

        # Crew list
        for w in self.crew_frame.winfo_children():
            w.destroy()
        if self.astronaut_data:
            # Group by craft
            craft_dict: dict[str, list[str]] = {}
            for person in self.astronaut_data:
                craft = person.get("craft", "Unknown")
                craft_dict.setdefault(craft, []).append(person["name"])

            for craft, names in craft_dict.items():
                tk.Label(
                    self.crew_frame, text=f"  {craft}",
                    bg=C_PANEL, fg=C_ACCENT,
                    font=("Consolas", 8, "bold"), anchor="w"
                ).pack(fill="x")
                for name in names:
                    tk.Label(
                        self.crew_frame, text=f"    · {name}",
                        bg=C_PANEL, fg=C_TEXT,
                        font=("Consolas", 8), anchor="w"
                    ).pack(fill="x")
        else:
            tk.Label(
                self.crew_frame, text="  No data available",
                bg=C_PANEL, fg=C_MUTED, font=("Consolas", 9)
            ).pack()

        # Earth Events list
        for w in self.events_frame.winfo_children():
            w.destroy()
        if self.earth_events:
            for event in self.earth_events[:5]: # Limit to 5 for UI space
                tk.Label(
                    self.events_frame, text=f"• {event['title']}",
                    bg=C_PANEL, fg=C_TEXT, font=("Consolas", 8),
                    anchor="w", justify="left", wraplength=220
                ).pack(fill="x", pady=1)
        else:
            tk.Label(self.events_frame, text="  No active events", bg=C_PANEL, fg=C_MUTED, font=("Consolas", 8)).pack()

        # APOD info
        for w in self.apod_frame.winfo_children():
            w.destroy()
        if self.apod_data:
            title = self.apod_data.get("title", "Unknown")
            tk.Label(
                self.apod_frame, text=title,
                bg=C_PANEL, fg=C_ACCENT, font=("Consolas", 8, "bold"),
                anchor="w", justify="left", wraplength=220
            ).pack(fill="x")
            date = self.apod_data.get("date", "")
            tk.Label(self.apod_frame, text=date, bg=C_PANEL, fg=C_MUTED, font=("Consolas", 7)).pack(anchor="w")
            
            if self.apod_img_data and PIL_AVAILABLE:
                try:
                    img = Image.open(io.BytesIO(self.apod_img_data))
                    img.thumbnail((250, 250), Image.LANCZOS)
                    self.apod_photoimage = ImageTk.PhotoImage(img)
                    img_label = tk.Label(self.apod_frame, image=self.apod_photoimage, bg=C_PANEL)
                    img_label.pack(pady=4)
                except Exception as e:
                    pass

        # Other spacecraft
        for w in self.other_frame.winfo_children():
            w.destroy()
        other_crafts = set()
        for p in self.astronaut_data:
            craft = p.get("craft", "")
            if craft and craft != "ISS":
                other_crafts.add(craft)
        if other_crafts:
            for craft in sorted(other_crafts):
                crew_on = [p["name"] for p in self.astronaut_data if p.get("craft") == craft]
                tk.Label(
                    self.other_frame,
                    text=f"  🚀 {craft}  ({len(crew_on)} crew)",
                    bg=C_PANEL, fg=C_ACCENT2,
                    font=("Consolas", 9, "bold"), anchor="w"
                ).pack(fill="x")
                for name in crew_on:
                    tk.Label(
                        self.other_frame,
                        text=f"    · {name}",
                        bg=C_PANEL, fg=C_TEXT,
                        font=("Consolas", 8), anchor="w"
                    ).pack(fill="x")
        else:
            tk.Label(
                self.other_frame,
                text="  ISS is the only crewed\n  spacecraft currently",
                bg=C_PANEL, fg=C_MUTED,
                font=("Consolas", 8), justify="left"
            ).pack(anchor="w", padx=4)
            
        # Update Day/Night Terminator first (so it stays in background)
        self._update_terminator()

        # Update event markers on map
        for marker in self.event_markers:
            marker.delete()
        self.event_markers.clear()
        
        for event in self.earth_events[:10]:
            try:
                geom = event['geometry'][0]
                if geom['type'] == 'Point':
                    lon, lat = geom['coordinates']
                    m = self.map_widget.set_marker(lat, lon, text=event['title'][:15]+"...", marker_color="#ff4444")
                    self.event_markers.append(m)
            except:
                pass

        # Update map widget
        if self.iss_data:

            lat = float(self.iss_data.get("latitude",  0))
            lon = float(self.iss_data.get("longitude", 0))
            
            marker_text = self.active_sat_name.split()[0]
            if not self.sat_marker:
                if self.sat_icon:
                    self.sat_marker = self.map_widget.set_marker(lat, lon, text=marker_text, icon=self.sat_icon)
                else:
                    self.sat_marker = self.map_widget.set_marker(lat, lon, text=marker_text)
            else:
                self.sat_marker.set_position(lat, lon)
                self.sat_marker.set_text(marker_text)
                
            # Update trail path
            if len(self.trail) > 1:
                if self.trail_path:
                    self.trail_path.set_position_list(self.trail)
                else:
                    self.trail_path = self.map_widget.set_path(self.trail, color=C_TRAIL, width=2)
                    

    def _update_terminator(self):
        now = datetime.now(timezone.utc)
        day_of_year = now.timetuple().tm_yday
        gamma = 2 * math.pi / 365 * (day_of_year - 1 + (now.hour - 12) / 24)
        decl = 0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma) - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma) - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma)
        eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma) - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
        tst = now.hour * 60 + now.minute + now.second / 60 + eqtime
        subsolar_lon = -((tst / 4) - 180)
        
        points = []
        for lon in range(-180, 182, 2):
            val = -1 / math.tan(decl) * math.cos(math.radians(lon - subsolar_lon))
            lat = math.degrees(math.atan(val))
            points.append((lat, lon))
            
        # Close the polygon to cover the night side
        # If declination > 0, North pole is in sunlight, so night side is at the South Pole (-85)
        pole = -85 if decl > 0 else 85
        points.append((pole, 180))
        points.append((pole, -180))
            
        # Update polygon points
        self.terminator_poly.position_list = points
        self.terminator_poly.draw()
# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Check dependencies
    missing = []
    try:
        import requests
    except ImportError:
        missing.append("requests")
    if not PIL_AVAILABLE:
        print("⚠  Pillow (PIL) not found — map image won't load. Install with: pip install pillow")

    if missing:
        print(f"❌  Missing required packages: {', '.join(missing)}")
        print(f"    Install with: pip install {' '.join(missing)}")
        sys.exit(1)

    app = ISSTracker()
    app.mainloop()
