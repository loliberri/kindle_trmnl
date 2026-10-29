
import argparse
import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

# Kindle 4 screen dimensions
W, H = 800, 600

WHITE = 255
BLACK = 0
GREY = 90
LIGHT_GREY = 175

# Location settings can be overridden with environment variables.
LAT = float(os.environ.get("KD_LAT", "53.35"))
LON = float(os.environ.get("KD_LON", "-6.26"))
CITY = os.environ.get("KD_CITY", "Dublin")
TIMEZONE = os.environ.get("KD_TIMEZONE", "Europe/Dublin")

FONT_PATHS = {
    "regular": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ],
    "bold": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ],
}


def load_font(weight, size):
    """Load a font available on GitHub's Ubuntu runner."""
    for path in FONT_PATHS[weight]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    return ImageFont.load_default()


F_TITLE = load_font("bold", 29)
F_HEADING = load_font("bold", 25)
F_TEMP = load_font("bold", 39)
F_NORMAL = load_font("regular", 18)
F_SMALL = load_font("regular", 16)
F_RAIN = load_font("bold", 17)


WEATHER_CODES = {
    0: "Clear",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Showers",
    81: "Showers",
    82: "Heavy showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm",
    99: "Heavy thunderstorm",
}


def fetch_weather():
    """Fetch today's and tomorrow's weather and hourly rain forecasts."""
    params = {
        "latitude": LAT,
        "longitude": LON,
        "timezone": TIMEZONE,
        "forecast_days": 2,
        "temperature_unit": "celsius",
        "current": "temperature_2m,weather_code",
        "daily": (
            "weather_code,"
            "temperature_2m_max,"
            "temperature_2m_min"
        ),
        "hourly": (
            "precipitation_probability,"
            "precipitation,"
            "weather_code"
        ),
    }

    url = (
        "https://api.open-meteo.com/v1/forecast?"
        + urllib.parse.urlencode(params)
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "KindleWeatherDashboard/1.0"},
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def rain_label(probability, amount):
    """Format hourly rain probability and expected precipitation."""
    if probability is None:
        probability_text = "--"
    else:
        probability_text = f"{round(probability)}%"

    if amount is None:
        amount_text = ""
    else:
        amount_text = f"{amount:.1f}mm"

    return probability_text, amount_text


def fit_text(draw, text, font, max_width):
    """Shorten text when necessary to fit the screen."""
    text = str(text)

    if draw.textlength(text, font=font) <= max_width:
        return text

    while text and draw.textlength(text + "...", font=font) > max_width:
        text = text[:-1]

    return text.rstrip() + "..."


def draw_rain_section(draw, weather, date_string, x, y, width):
    """Draw rain forecasts at 6–9am and 3–6pm for one day."""
    hourly = weather.get("hourly", {})
    times = hourly.get("time", [])

    probabilities = hourly.get("precipitation_probability", [])
    amounts = hourly.get("precipitation", [])

    # Match forecast times to their array positions.
    positions = {
        timestamp: index
        for index, timestamp in enumerate(times)
    }

    requested_hours = [6, 7, 8, 9, 15, 16, 17, 18]

    draw.text(
        (x, y),
        "HOURLY RAIN",
        font=F_HEADING,
        fill=BLACK,
    )

    y += 34

    # Split the eight hours into morning and afternoon.
    groups = [
        ("MORNING", requested_hours[:4]),
        ("AFTERNOON", requested_hours[4:]),
    ]

    label_width = 92
    gap = 5
    cell_width = (width - label_width - 3 * gap) // 4

    for group_name, hours in groups:
        draw.text(
            (x, y + 7),
            group_name,
            font=F_SMALL,
            fill=GREY,
        )

        for i, hour in enumerate(hours):
            cell_x = x + label_width + i * (cell_width + gap)

            draw.rectangle(
                (
                    cell_x,
                    y,
                    cell_x + cell_width,
                    y + 65,
                ),
                outline=LIGHT_GREY,
                width=1,
            )

            draw.text(
                (cell_x + 5, y + 5),
                f"{hour:02d}:00",
                font=F_SMALL,
                fill=BLACK,
            )

            timestamp = f"{date_string}T{hour:02d}:00"
            index = positions.get(timestamp)

            if index is not None:
                probability = (
                    probabilities[index]
                    if index < len(probabilities)
                    else None
                )
                amount = (
                    amounts[index]
                    if index < len(amounts)
                    else None
                )
            else:
                probability = None
                amount = None

            probability_text, amount_text = rain_label(
                probability, amount
            )

            draw.text(
                (cell_x + 5, y + 29),
                probability_text,
                font=F_RAIN,
                fill=BLACK,
            )

            draw.text(
                (cell_x + 5, y + 48),
                amount_text,
                font=F_SMALL,
                fill=GREY,
            )

        y += 72


def draw_dashboard(output_path):
    """Create the 800 x 600 Kindle dashboard image."""
    image = Image.new("L", (W, H), WHITE)
    draw = ImageDraw.Draw(image)

    now = dt.datetime.now(ZoneInfo(TIMEZONE))

    # Header: day, date and location on one line.
    header = (
        f"{now.strftime('%A')} {now.day} "
        f"{now.strftime('%B %Y')}  |  {CITY}"
    )

    draw.text(
        (25, 15),
        fit_text(draw, header, F_TITLE, W - 50),
        font=F_TITLE,
        fill=BLACK,
    )

    draw.line((25, 58, W - 25, 58), fill=BLACK, width=3)

    try:
        weather = fetch_weather()
        current = weather["current"]
        daily = weather["daily"]
        dates = daily["time"]

        today_date = dates[0]
        tomorrow_date = dates[1]

        today = {
            "temperature": round(current["temperature_2m"]),
            "condition": WEATHER_CODES.get(
                current["weather_code"], "Unknown"
            ),
            "high": round(daily["temperature_2m_max"][0]),
            "low": round(daily["temperature_2m_min"][0]),
        }

        tomorrow = {
            "temperature": None,
            "condition": WEATHER_CODES.get(
                daily["weather_code"][1], "Unknown"
            ),
            "high": round(daily["temperature_2m_max"][1]),
            "low": round(daily["temperature_2m_min"][1]),
        }

        # Weather headings.
        column_width = 360
        left_x = 30
        right_x = 410

        draw.text(
            (left_x, 75),
            "TODAY",
            font=F_HEADING,
            fill=BLACK,
        )

        draw.text(
            (right_x, 75),
            "TOMORROW",
            font=F_HEADING,
            fill=BLACK,
        )

        # Today's weather.
        draw.text(
            (left_x, 110),
            f"{today['temperature']}°C",
            font=F_TEMP,
            fill=BLACK,
        )

        draw.text(
            (left_x, 158),
            fit_text(draw, today["condition"], F_NORMAL, 350),
            font=F_NORMAL,
            fill=GREY,
        )

        draw.text(
            (left_x, 185),
            f"High {today['high']}°  Low {today['low']}°",
            font=F_NORMAL,
            fill=BLACK,
        )

        # Tomorrow's forecast.
        draw.text(
            (right_x, 110),
            f"High {tomorrow['high']}°",
            font=F_TEMP,
            fill=BLACK,
        )

        draw.text(
            (right_x, 158),
            fit_text(
                draw, tomorrow["condition"], F_NORMAL, 350
            ),
            font=F_NORMAL,
            fill=GREY,
        )

        draw.text(
            (right_x, 185),
            f"Low {tomorrow['low']}°",
            font=F_NORMAL,
            fill=BLACK,
        )

        draw.line((25, 220, W - 25, 220), fill=BLACK, width=2)

        # Hourly rain forecast for each day.
        draw_rain_section(
            draw, weather, today_date, left_x, 235, column_width
        )

        draw_rain_section(
            draw, weather, tomorrow_date, right_x, 235, column_width
        )

        # Footer.
        draw.line((25, 565, W - 25, 565), fill=LIGHT_GREY, width=1)

        draw.text(
            (25, 573),
            "Rain: probability (%) and expected amount (mm)",
            font=F_SMALL,
            fill=GREY,
        )

    except Exception as error:
        draw.text(
            (30, 100),
            "Weather forecast unavailable",
            font=F_HEADING,
            fill=BLACK,
        )

        draw.text(
            (30, 145),
            "Please check the internet connection",
            font=F_NORMAL,
            fill=GREY,
        )

        print(f"Weather error: {error}")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    image.save(output_path, format="PNG")
    print(f"Dashboard saved to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="combo")
    parser.add_argument("--out", default="docs/kindle.png")
    args = parser.parse_args()

    draw_dashboard(args.out)
