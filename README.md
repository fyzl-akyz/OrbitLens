# OrbitLens: Live ISS & Space Dashboard 🛰️

OrbitLens is a real-time tracking dashboard for the International Space Station (ISS) and other space-related data. Built with Python and Tkinter, it provides a highly visual, interactive, and informative experience for space enthusiasts.

## Features ✨

*   **Live ISS Tracking**: Real-time position (latitude, longitude, altitude, velocity) of the International Space Station, rendered on an interactive map.
*   **Day/Night Terminator**: Visual representation of the Earth's day and night cycles dynamically projected onto the map.
*   **Crew in Space**: Live list of astronauts currently aboard the ISS and other spacecraft.
*   **NASA Earth Events (EONET)**: Real-time mapping of natural events (wildfires, storms, volcanoes) using the NASA Earth Observatory Natural Event Tracker API.
*   **Astronomy Picture of the Day (APOD)**: Daily high-resolution space imagery fetched directly from NASA's APOD API, displayed in a scrollable sidebar.

## Data Sources 📡

OrbitLens relies on the following public APIs:
*   [Open-Notify](http://open-notify.org/) (ISS Position & Astronauts)
*   [Where the ISS at?](https://wheretheiss.at/) (Extended ISS metrics)
*   [NASA EONET](https://eonet.gsfc.nasa.gov/) (Earth Events)
*   [NASA APOD](https://api.nasa.gov/) (Astronomy Images)

## Installation & Setup 🛠️

1. **Clone the repository:**
   ```bash
   git clone https://github.com/fyzl-akyz/orbitlens.git
   cd orbitlens
   ```

2. **Install required dependencies:**
   Make sure you have Python 3.x installed. Then, install the required packages using pip:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application:**
   ```bash
   python iss_tracker.py
   ```

## Note on API Limits ⚠️
The NASA APOD feature currently uses a `DEMO_KEY`. If you plan on using the application heavily, consider obtaining your own free API key from [api.nasa.gov](https://api.nasa.gov/) and replacing it in the `iss_tracker.py` file.

## License 📄
This project is open-source and available under the MIT License.
