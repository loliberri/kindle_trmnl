import argparse
import datetime as dt
import json
import os
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont


# ============================================================
# DASHBOARD SETTINGS
# ============================================================

W = 800
H = 600

BLACK = 0
WHITE = 255

TIMEZONE = "Europe/Dublin"

LATITUDE = float(os.environ.get("KD_LAT", "53.35"))
LONGITUDE = float(os.environ.get("KD_LON", "-6.27"))
CITY = os.environ.get("KD_CITY", "Dublin")


# ============================================================
# FONT SETTINGS
# ============================================================

def load_font(style, size):
    """Load a font available on GitHub Actions or Windows."""

    possible_fonts = {
        "bold": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ],
        "regular": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ],
    }

    for font_path in possible_fonts.get(style, []):
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)

    return ImageFont.load_default()


F_TITLE = load_font("bold", 28)
F_HEADING = load_font("bold", 21)
F_TEMP = load_font("bold", 38)
F_NORMAL = load_font("regular", 17)
F_SMALL = load_font("regular", 15)
F_TINY = load_font("regular", 12)


# ============================================================
# WEATHER CODE DESCRIPTIONS
# ============================================================

WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Freezing drizzle",
    57: "Heavy freezing drizzle",
    61: "Light rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Heavy freezing rain",
    71: "Light snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Moderate rain showers",
    82: "Heavy rain showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Heavy thunderstorm with hail",
}


# ============================================================
# WEATHER DATA
# ============================================================

def fetch_weather():
    """Retrieve today's and tomorrow's forecast from Open-Meteo."""

    parameters = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "timezone": TIMEZONE,
        "forecast_days": 2,
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "apparent_temperature,"
            "is_day,"
            "precipitation,"
            "weather_code"
        ),
        "daily": (
            "weather_code,"
            "temperature_2m_max,"
            "temperature_2m_min,"
            "precipitation_probability_max,"
            "precipitation_sum"
        ),
        "hourly": (
            "temperature_2m,"
            "precipitation_probability,"
            "precipitation,"
            "weather_code"
        ),
    }

    url = (
        "https://api.open-meteo.com/v1/forecast?"
        + urllib.parse.urlencode(parameters)
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "KindleWeatherDashboard/1.0"},
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def weather_description(code):
    """Convert a weather code into a readable description."""

    if code is None:
        return "Weather unavailable"

    return WEATHER_CODES.get(int(code), "Unknown conditions")


def format_temperature(value):
    """Format a temperature in Celsius."""

    if value is None:
        return "--°C"

    return f"{round(value)}°C"


def format_hour(hour):
    """Convert a 24-hour number to a label such as 6am or 5pm."""

    suffix = "am" if hour < 12 else "pm"
    hour_12 = hour % 12 or 12

    return f"{hour_12}{suffix}"


def rain_label(probability, amount):
    """Create a short precipitation summary."""

    if probability is None:
        probability_text = "?"
    else:
        probability_text = f"{round(probability)}%"

    if amount is None:
        amount_text = ""
    else:
        amount_text = f" | {amount:.1f}mm"

    return f"Rain: {probability_text}{amount_text}"


# ============================================================
# TEXT HELPERS
# ============================================================

def fit_text(draw, text, font, max_width):
    """Shorten text until it fits within the available width."""

    text = str(text)

    if draw.textlength(text, font=font) <= max_width:
        return text

    while text and draw.textlength(
        text + "...", font=font
    ) > max_width:
        text = text[:-1]

    return text + "..." if text else "..."


def wrap_text(draw, text, font, max_width):
    """Wrap text into lines that fit within a specified width."""

    words = str(text).split()
    lines = []
    current_line = ""

    for word in words:
        candidate = f"{current_line} {word}".strip()

        if draw.textlength(candidate, font=font) <= max_width:
            current_line = candidate
        else:
            if current_line:
                lines.append(current_line)

            if draw.textlength(word, font=font) > max_width:
                lines.append(fit_text(draw, word, font, max_width))
                current_line = ""
            else:
                current_line = word

    if current_line:
        lines.append(current_line)

    return lines


def format_date_heading(date_value):
    """Format a date without relying on platform-specific %-d."""

    return f"{date_value.strftime('%a')} {date_value.day} {date_value.strftime('%b')}"


# ============================================================
# RANDOM FACT
# ============================================================

class FactParser(HTMLParser):
    """Extract headings from the Random Fact Generator webpage."""

    def __init__(self):
        super().__init__()
        self.in_heading = False
        self.heading_parts = []
        self.headings = []

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3"):
            self.in_heading = True
            self.heading_parts = []

    def handle_data(self, data):
        if self.in_heading:
            self.heading_parts.append(data.strip())

    def handle_endtag(self, tag):
        if self.in_heading and tag in ("h1", "h2", "h3"):
            heading = " ".join(
                part for part in self.heading_parts if part
            )

            if heading:
                self.headings.append(heading)

            self.in_heading = False


def get_random_fact():
    """
    Attempt to retrieve a fact from Random Fact Generator.

    If the website cannot be accessed or the page structure changes,
    return a fallback message so dashboard generation can continue.
    """

    url = "https://www.randomfactgenerator.com/"

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 KindleWeatherDashboard/1.0"
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            html = response.read().decode(
                "utf-8",
                errors="replace",
            )

        parser = FactParser()
        parser.feed(html)

        candidates = [
            heading
            for heading in parser.headings
            if heading.strip().lower() != "random fact generator"
        ]

        if candidates:
            fact = re.sub(r"\s+", " ", candidates[0]).strip()
            return fact

        print("Random fact: no suitable heading found.")

        return "Visit randomfactgenerator.com for a random fact."

    except Exception as error:
        print(f"Random fact error: {error}")

        return "Random fact temporarily unavailable."


# ============================================================
# COMPACT HOURLY RAIN FORECAST
# ============================================================

def draw_rain_section(draw, weather, date_string, x, y, width):
    """
    Draw compact hourly rain forecast boxes.

    The RAIN FORECAST heading has been removed.

    Morning hours: 6am, 7am, 8am, 9am
    Afternoon hours: 3pm, 4pm, 5pm, 6pm
    """

    hourly = weather.get("hourly", {})
    hourly_times = hourly.get("time", [])
    rain_probabilities = hourly.get("precipitation_probability", [])
    hourly_codes = hourly.get("weather_code", [])

    # No large heading: start directly with the morning row.
    y += 5

    hour_groups = [
        ("MORNING", [6, 7, 8, 9]),
        ("AFTERNOON", [15, 16, 17, 18]),
    ]

    cell_gap = 5
    cell_width = (width - cell_gap * 3) // 4
    cell_height = 48

    for group_name, hours in hour_groups:

        # Smaller group label to avoid overlapping the boxes.
        draw.text(
            (x, y + 2),
            group_name,
            font=F_TINY,
            fill=BLACK,
        )

        y += 15

        for index, hour in enumerate(hours):
            cell_x = x + index * (cell_width + cell_gap)

            draw.rectangle(
                (
                    cell_x,
                    y,
                    cell_x + cell_width,
                    y + cell_height,
                ),
                outline=BLACK,
                width=1,
            )

            # Hour label, e.g. 6am or 5pm.
            draw.text(
                (cell_x + 5, y + 2),
                format_hour(hour),
                font=F_SMALL,
                fill=BLACK,
            )

            matching_index = None

            for i, timestamp in enumerate(hourly_times):
                if timestamp.startswith(date_string) and len(timestamp) >= 13:
                    try:
                        timestamp_hour = int(timestamp[11:13])

                        if timestamp_hour == hour:
                            matching_index = i
                            break

                    except ValueError:
                        continue

            if matching_index is not None:
                probability = rain_probabilities[matching_index]
                code = hourly_codes[matching_index]

                if probability is None:
                    probability_text = "--%"
                else:
                    probability_text = f"{round(probability)}%"

                draw.text(
                    (cell_x + 5, y + 19),
                    probability_text,
                    font=F_SMALL,
                    fill=BLACK,
                )

                description = weather_description(code)

                draw.text(
                    (cell_x + 5, y + 34),
                    fit_text(
                        draw,
                        description,
                        F_TINY,
                        cell_width - 10,
                    ),
                    font=F_TINY,
                    fill=BLACK,
                )

            else:
                draw.text(
                    (cell_x + 5, y + 19),
                    "--%",
                    font=F_SMALL,
                    fill=BLACK,
                )

        y += cell_height + 10


# ============================================================
# DASHBOARD RENDERING
# ============================================================

def draw_dashboard(output_path):
    """Create the complete 800 x 600 Kindle dashboard image."""

    print("Fetching weather forecast...")

    weather = fetch_weather()

    current = weather.get("current", {})
    daily = weather.get("daily", {})
    daily_dates = daily.get("time", [])

    if len(daily_dates) < 2:
        raise RuntimeError(
            "Weather service did not return forecasts for two days."
        )

    today_date = daily_dates[0]
    tomorrow_date = daily_dates[1]

    today = dt.date.fromisoformat(today_date)
    tomorrow = dt.date.fromisoformat(tomorrow_date)

    try:
        now = dt.datetime.now(ZoneInfo(TIMEZONE))
    except Exception:
        now = dt.datetime.now()

    image = Image.new("L", (W, H), WHITE)
    draw = ImageDraw.Draw(image)

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    header_text = (
        f"{now.strftime('%A')} "
        f"{now.day} {now.strftime('%B %Y')} | {CITY}"
    )

    draw.text(
        (25, 18),
        fit_text(draw, header_text, F_TITLE, W - 50),
        font=F_TITLE,
        fill=BLACK,
    )

    draw.line(
        (25, 60, W - 25, 60),
        fill=BLACK,
        width=2,
    )

    # --------------------------------------------------------
    # CURRENT CONDITIONS
    # --------------------------------------------------------

    current_temperature = current.get("temperature_2m")
    current_code = current.get("weather_code")
    feels_like = current.get("apparent_temperature")
    humidity = current.get("relative_humidity_2m")

    draw.text(
        (30, 72),
        "CURRENT CONDITIONS",
        font=F_HEADING,
        fill=BLACK,
    )

    draw.text(
        (30, 105),
        format_temperature(current_temperature),
        font=F_TEMP,
        fill=BLACK,
    )

    draw.text(
        (200, 115),
        fit_text(
            draw,
            weather_description(current_code),
            F_NORMAL,
            300,
        ),
        font=F_NORMAL,
        fill=BLACK,
    )

    if feels_like is not None:
        draw.text(
            (200, 143),
            f"Feels like {format_temperature(feels_like)}",
            font=F_SMALL,
            fill=BLACK,
        )

    if humidity is not None:
        draw.text(
            (480, 115),
            f"Humidity: {humidity}%",
            font=F_SMALL,
            fill=BLACK,
        )

    # --------------------------------------------------------
    # TODAY AND TOMORROW FORECASTS
    # --------------------------------------------------------

    column_width = 360
    left_x = 30
    right_x = 410

    draw.line(
        (400, 175, 400, 435),
        fill=BLACK,
        width=1,
    )

    # TODAY
    draw.text(
        (left_x, 180),
        f"TODAY - {format_date_heading(today)}",
        font=F_HEADING,
        fill=BLACK,
    )

    today_high = daily["temperature_2m_max"][0]
    today_low = daily["temperature_2m_min"][0]
    today_code = daily["weather_code"][0]

    draw.text(
        (left_x, 210),
        f"{format_temperature(today_high)} / "
        f"{format_temperature(today_low)}",
        font=F_NORMAL,
        fill=BLACK,
    )

    draw.text(
        (left_x, 237),
        fit_text(
            draw,
            weather_description(today_code),
            F_SMALL,
            column_width,
        ),
        font=F_SMALL,
        fill=BLACK,
    )

    today_rain_probability = daily.get(
        "precipitation_probability_max",
        [None, None],
    )[0]

    today_rain_amount = daily.get(
        "precipitation_sum",
        [None, None],
    )[0]

    draw.text(
        (left_x, 258),
        fit_text(
            draw,
            rain_label(
                today_rain_probability,
                today_rain_amount,
            ),
            F_SMALL,
            column_width,
        ),
        font=F_SMALL,
        fill=BLACK,
    )

    # TOMORROW
    draw.text(
        (right_x, 180),
        f"TOMORROW - {format_date_heading(tomorrow)}",
        font=F_HEADING,
        fill=BLACK,
    )

    tomorrow_high = daily["temperature_2m_max"][1]
    tomorrow_low = daily["temperature_2m_min"][1]
    tomorrow_code = daily["weather_code"][1]

    draw.text(
        (right_x, 210),
        f"{format_temperature(tomorrow_high)} / "
        f"{format_temperature(tomorrow_low)}",
        font=F_NORMAL,
        fill=BLACK,
    )

    draw.text(
        (right_x, 237),
        fit_text(
            draw,
            weather_description(tomorrow_code),
            F_SMALL,
            column_width,
        ),
        font=F_SMALL,
        fill=BLACK,
    )

    tomorrow_rain_probability = daily.get(
        "precipitation_probability_max",
        [None, None],
    )[1]

    tomorrow_rain_amount = daily.get(
        "precipitation_sum",
        [None, None],
    )[1]

    draw.text(
        (right_x, 258),
        fit_text(
            draw,
            rain_label(
                tomorrow_rain_probability,
                tomorrow_rain_amount,
            ),
            F_SMALL,
            column_width,
        ),
        font=F_SMALL,
        fill=BLACK,
    )

    # --------------------------------------------------------
    # COMPACT HOURLY RAIN BOXES
    # --------------------------------------------------------

    draw_rain_section(
        draw,
        weather,
        today_date,
        left_x,
        290,
        column_width,
    )

    draw_rain_section(
        draw,
        weather,
        tomorrow_date,
        right_x,
        290,
        column_width,
    )

    # --------------------------------------------------------
    # SHORT DID YOU KNOW? SECTION
    # --------------------------------------------------------

    draw.line(
        (25, 440, W - 25, 440),
        fill=BLACK,
        width=1,
    )

    draw.text(
        (30, 447),
        "DID YOU KNOW?",
        font=F_SMALL,
        fill=BLACK,
    )

    print("Fetching a random fact...")

    fact = get_random_fact()

    # Limit the fact to keep the layout compact.
    max_fact_characters = 120

    if len(fact) > max_fact_characters:
        fact = fact[:max_fact_characters].rsplit(" ", 1)[0] + "..."

    fact_lines = wrap_text(
        draw,
        fact,
        F_TINY,
        W - 60,
    )

    # Display no more than two lines.
    for index, line in enumerate(fact_lines[:2]):
        draw.text(
            (30, 468 + index * 16),
            line,
            font=F_TINY,
            fill=BLACK,
        )

    # --------------------------------------------------------
    # FOOTER
    # --------------------------------------------------------

    draw.line(
        (25, 555, W - 25, 555),
        fill=BLACK,
        width=1,
    )

    footer_text = (
        f"Updated {now.strftime('%H:%M')} | Weather: Open-Meteo"
    )

    draw.text(
        (30, 560),
        fit_text(draw, footer_text, F_TINY, W - 60),
        font=F_TINY,
        fill=BLACK,
    )

    # --------------------------------------------------------
    # SAVE IMAGE
    # --------------------------------------------------------

    output_directory = os.path.dirname(output_path)

    if output_directory:
        os.makedirs(output_directory, exist_ok=True)

    image.save(output_path, format="PNG")

    print(f"Dashboard saved to: {output_path}")


# ============================================================
# MAIN PROGRAM
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate the Kindle weather dashboard."
    )

    parser.add_argument(
        "--mode",
        default="combo",
        help="Dashboard mode (retained for workflow compatibility).",
    )

    parser.add_argument(
        "--out",
        default="docs/kindle.png",
        help="Output PNG path.",
    )

    args = parser.parse_args()

    try:
        draw_dashboard(args.out)

    except Exception as error:
        print(f"Dashboard generation failed: {error}")
        raise


if __name__ == "__main__":
    main()
