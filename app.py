from flask import Flask, render_template, request
import requests
import time
import datetime

app = Flask(__name__)

GOOGLE_MAPS_API_KEY = "API-key"
SERPAPI_API_KEY = "API-key"


@app.route('/')
def home():
    """
    Render de startpagina van de applicatie.

    Returns:
        str: HTML-inhoud van de indexpagina.
    """
    return render_template('index.html')


@app.route('/results', methods=['GET', 'POST'])
def search():
    """
    Verwerk het zoekformulier en toon reisopties op basis van de ingevoerde gegevens.

    Returns:
        str: HTML-inhoud van de resultatenpagina met reisopties.
    """
    if request.method == 'POST':
        origin, destination, departure_date, return_date, departure_time = get_form_data(
            request)
        departure_timestamp = get_departure_timestamp(departure_date,
                                                      departure_time)
        origin_iata, destination_iata = get_iata_codes(origin,
                                                       destination)
        travel_options = calculate_travel_options(origin, destination,
                                                  origin_iata,
                                                  destination_iata,
                                                  departure_date,
                                                  return_date,
                                                  departure_timestamp)
        return render_template('results.html', origin=origin,
                               destination=destination,
                               travel_options=travel_options)
    else:
        return render_template('results.html', origin=[],
                               destination=[], travel_options=[])


def get_form_data(request):
    """
    Haal gegevens op uit het formulier.

    Args:
        request: HTTP-verzoek object.

    Returns:
        tuple: Gegevens van vertrekplaats, bestemming, vertrekdatum, retourdatum en vertrektijd.
    """
    origin = request.form.get('origin')
    destination = request.form.get('destination')
    departure_date = request.form.get('departure_date')
    return_date = request.form.get('return_date')
    departure_time = request.form.get('departure_time')
    return origin, destination, departure_date, return_date, departure_time


def get_departure_timestamp(departure_date, departure_time):
    """
    Combineer vertrekdatum en -tijd en converteer naar Unix-tijdstempel.

    Args:
        departure_date (str): Vertrekdatum in het formaat "YYYY-MM-DD".
        departure_time (str): Vertrektijd in het formaat "HH:MM".

    Returns:
        int: Unix-tijdstempel van de vertrekdatum en -tijd.
    """
    if departure_time:
        departure_datetime = f"{departure_date} {departure_time}"
        return int(time.mktime(
            datetime.datetime.strptime(departure_datetime,
                                       "%Y-%m-%d %H:%M").timetuple()))
    else:
        return int(time.mktime(
            datetime.datetime.strptime(departure_date,
                                       "%Y-%m-%d").timetuple()))


def get_iata_codes(origin, destination):
    """
    Haal IATA-codes op voor de vertrek- en aankomststeden.

    Args:
        origin (str): Vertrekstad.
        destination (str): Aankomststad.

    Returns:
        tuple: IATA-codes van de vertrek- en aankomststeden.
    """
    origin_iata = get_iata_code(origin)
    destination_iata = get_iata_code(destination)
    return origin_iata, destination_iata


def calculate_travel_options(origin, destination, origin_iata,
                             destination_iata, departure_date,
                             return_date, departure_timestamp):
    """
    Bereken de reisopties en retourneer een lijst met opties gesorteerd op CO2-uitstoot.

    Args:
        origin (str): Vertrekstad.
        destination (str): Aankomststad.
        origin_iata (str): IATA-code van vertrekstad.
        destination_iata (str): IATA-code van aankomststad.
        departure_date (str): Vertrekdatum.
        return_date (str): Retourdatum (optioneel).
        departure_timestamp (int): Unix-tijdstempel van vertrekdatum en -tijd.

    Returns:
        list: Lijst met beschikbare reisopties.
    """
    travel_options = []
    try:
        flight_data = get_flight_data(origin_iata, destination_iata,
                                      departure_date, return_date)
        if flight_data:
            travel_options.append(flight_data)

        driving_data = get_route_data(origin, destination, "driving",
                                      departure_timestamp)
        if driving_data:
            uitstoot = bereken_co2(driving_data['distance'], 'auto')
            travel_options.append({
                "type": "Auto",
                "time": driving_data['duration'],
                "distance": driving_data['distance'],
                "cost": "€0.25/km",
                "co2": uitstoot
            })

        transit_data = get_route_data(origin, destination, "transit",
                                      departure_timestamp)
        if transit_data:
            uitstoot = bereken_co2(driving_data['distance'], 'trein')
            travel_options.append({
                "type": "Trein",
                "time": transit_data['duration'],
                "distance": transit_data['distance'],
                "cost": "€10-€30",
                "co2": uitstoot
            })

        travel_options.extend([
            {
                "type": "Bus",
                "time": driving_data['duration'],
                "distance": driving_data['distance'],
                "cost": "€38",
                "co2": 95.0
            }
        ])

        travel_options.sort(key=lambda x: x['co2'])

    except Exception as e:
        raise Exception(
            f"Er ging iets mis bij het ophalen van routes: {e}")

    return travel_options


def get_route_data(origin, destination, mode, departure_time):
    """
    Haalt routegegevens op van de Google Maps Directions API.

    Args:
        origin (str): Vertrekstad.
        destination (str): Aankomststad.
        mode (str): Verkeersmodus (bijv. "driving", "transit").
        departure_time (int): Unix-tijdstempel van vertrekdatum en -tijd.

    Returns:
        dict: Informatie over de route (duur, afstand).
    """
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "key": GOOGLE_MAPS_API_KEY,
    }
    if mode == "transit" and departure_time:
        params["departure_time"] = departure_time

    response = requests.get(url, params=params)
    data = response.json()

    if data["status"] == "OK":
        route = data["routes"][0]["legs"][0]
        return {
            "duration": route["duration"]["text"],
            "distance": route["distance"]["text"]
        }

    else:
        # Log de foutmelding voor debugging
        print(
            f"Google Maps API Error [{mode}]: {data.get('error_message', 'Onbekende fout')}")
        return None


def get_flight_data(origin_iata, destination_iata, departure_date,
                    return_date=None):
    """
    Haal vluchtinformatie op van de SerpAPI.

    Args:
        origin_iata (str): IATA-code van vertrekstad.
        destination_iata (str): IATA-code van aankomststad.
        departure_date (str): Vertrekdatum.
        return_date (str): Retourdatum (optioneel).

    Returns:
        dict: Informatie over de vlucht (duur, kosten, CO2-uitstoot).
    """
    params = {
        "engine": "google_flights",
        "departure_id": origin_iata,
        "arrival_id": destination_iata,
        "outbound_date": departure_date,
        "return_date": return_date,
        "gl": "nl",
        "api_key": SERPAPI_API_KEY,
    }
    url = "https://serpapi.com/search?engine=google_flights"

    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()

        if 'best_flights' in data and len(data['best_flights']) > 0:
            flight = data['best_flights'][0]['flights'][0]
            carbon_emissions = \
            data['best_flights'][0]['carbon_emissions'][
                'this_flight'] / 1000  # Convert to kg
            price = data['best_flights'][0]['price']

            flight_duration_minutes = flight['duration']
            hours = flight_duration_minutes // 60
            minutes = flight_duration_minutes % 60
            flight_time = f"{hours} hours {minutes} mins"

            return {
                "type": "Vliegtuig",
                "time": flight_time,
                "distance": "N.V.T",
                "cost": f"€{price}",
                "co2": round(carbon_emissions, 2),
            }
        else:
            print("Geen vluchten gevonden.")
            return None
    else:
        print(
            f"Fout bij het ophalen van gegevens: {response.status_code}")
        print(response.text)
        return None


def get_iata_code(city):
    """
    Koppel een stad aan de bijbehorende IATA-code.

    Args:
        city (str): Naam van de stad.

    Returns:
        str: Bijbehorende IATA-code of None als de stad niet wordt gevonden.
    """
    city_to_iata = {
        "Amsterdam": "AMS",
        "Barcelona": "BCN",
        "Kopenhagen": "CPH",
        "Parijs": "CDG",
        "Berlijn": "BER"
    }
    return city_to_iata.get(city, None)


def bereken_co2(distance_km, vervoermiddel):
    """
    Bereken de CO2-uitstoot van een reis.

    Args:
        distance_km (str): Afstand in kilometers (bijv. "100 km").
        vervoermiddel (str): Type vervoermiddel ("auto", "vliegtuig", "trein", "boot").

    Returns:
        float: Totale CO2-uitstoot in kilogrammen.

    Raises:
        ValueError: Als het vervoermiddel ongeldig is.
    """
    EMISSION_FACTORS = {
        "auto": 0.192,
        "vliegtuig": 0.255,
        "trein": 0.041,
        "boot": 0.115
    }
    distance_km = float(distance_km.replace(" km", "").replace(",", ""))

    vervoermiddel = vervoermiddel.lower()
    if vervoermiddel not in EMISSION_FACTORS:
        raise ValueError(
            f"'{vervoermiddel}' is geen geldig vervoermiddel. Kies uit: {list(EMISSION_FACTORS.keys())}")

    uitstoot_per_km = EMISSION_FACTORS[vervoermiddel]
    totale_uitstoot = distance_km * uitstoot_per_km
    return round(totale_uitstoot, 2)


if __name__ == '__main__':
    app.run(debug=True)
