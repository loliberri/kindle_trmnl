```python
#!/usr/bin/env python3

"""Generate an 800x600 grayscale dashboard for Kindle 4."""

import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

# Kindle 4 dashboard dimensions
WIDTH = 800
HEIGHT = 600

BLACK = 0
GREY = 100
WHITE = 255

# Ireland's local time, including daylight-saving changes.
TIMEZONE = ZoneInfo("Europe/Dublin")

# Default location: Dublin, Ireland.
LAT = os.environ.get("KD_LAT", "53.35")
LON = os.environ.get("KD_LON", "-6.27")
CITY = os.environ.get("KD_CITY", "Dublin")

OUTPUT = Path("docs/kindle.png")

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def get_font(size, bold=False):
    """Load a font available on the GitHub runner."""
    path = FONT_BOLD if bold else FONT_REGULAR

    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


FONT_HUGE = get_font(145, True)
FONT_BIG = get_font(48, True)
FONT_MEDIUM = get_font(29, True)
FONT_SMALL = get_font(22)
FONT_TINY = get_font(18)


def get_weather():
    """Retrieve current conditions and today's/tomorrow's forecast."""

    params = {
        "latitude": LAT,
        "longitude": LON,
        "current": "temperature_2m,weather_code",
        "daily": (
            "weather_code,"
            "temperature_2m_max,"
            "temperature_2m_min"
        ),
        "temperature_unit": "celsius",
        "forecast_days": 2,
        "timezone": "Europe/Dublin",
    }

    url = (
        "https://api.open-meteo.com/v1/forecast?"
        + urllib.parse.urlencode(params)
    )

    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "KindleDashboard/1.0"},
        )

        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.load(response)

        current = data["current"]
        daily = data["daily"]

        return {
            "temperature": round(current["temperature_2m"]),
            "condition": describe_weather(current["weather_code"]),
            "today_high": round(daily["temperature_2m_max"][0]),
            "today_low": round(daily["temperature_2m_min"][0]),
            "tomorrow_condition": describe_weather(
                daily["weather_code"][1]
            ),
            "tomorrow_high": round(
                daily["temperature_2m_max"][1]
            ),
            "tomorrow_low": round(
                daily["temperature_2m_min"][1]
            ),
        }

    except Exception as error:
        print(f"Weather unavailable: {error}")

        return {
            "temperature": "--",
            "condition": "Unavailable",
            "today_high": "--",
            "today_low": "--",
            "tomorrow_condition": "Unavailable",
            "tomorrow_high": "--",
            "tomorrow_low": "--",
        }


def describe_weather(code):
    """Convert Open-Meteo weather codes into readable descriptions."""

    descriptions = {
        0: "Clear",
        1: "Mostly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Fog",
        51: "Light drizzle",
        53: "Drizzle",
        55: "Heavy drizzle",
        61: "Light rain",
        63: "Rain",
        65: "Heavy rain",
        71: "Light snow",
        73: "Snow",
        75: "Heavy snow",
        80: "Rain showers",
        81: "Rain showers",
        82: "Heavy showers",
        95: "Thunderstorm",
        96: "Thunderstorm",
        99: "Heavy thunderstorm",
    }

    return descriptions.get(code, "Unknown")


def get_next_event():
    """Read a simple ICS calendar feed if KD_ICS is configured."""

    calendar_url = os.environ.get("KD_ICS", "").strip()

    if not calendar_url:
        return "Calendar: not configured"

    try:
        request = urllib.request.Request(
            calendar_url,
            headers={"User-Agent": "KindleDashboard/1.0"},
        )

        with urllib.request.urlopen(request, timeout=15) as response:
            content = response.read().decode("utf-8", "replace")

        # Unfold calendar lines split across multiple physical lines.
        lines = []

        for line in content.splitlines():
            if line.startswith((" ", "\t")) and lines:
                lines[-1] += line[1:]
            else:
                lines.append(line)

        events = []
        event = None

        for line in lines:
            if line == "BEGIN:VEVENT":
                event = {}

            elif line == "END:VEVENT" and event is not None:
                if event.get("start") and event.get("summary"):
                    events.append(event)
                event = None

            elif event is not None and ":" in line:
                key, value = line.split(":", 1)
                key = key.split(";", 1)[0]

                if key == "DTSTART":
                    event["start"] = parse_calendar_date(value)

                elif key == "SUMMARY":
                    event["summary"] = (
                        value.replace("\\,", ",")
                        .replace("\\;", ";")
                        .replace("\\n", " ")
                    )

        now = dt.datetime.now(TIMEZONE)

        upcoming = [
            item for item in events
            if item["start"] is not None
            and item["start"] >= now
        ]

        upcoming.sort(key=lambda item: item["start"])

        if not upcoming:
            return "No upcoming calendar events"

        first = upcoming[0]
        start = first["start"]

        return (
            f"Next: {start.strftime('%a %d %b')} "
            f"{start.strftime('%H:%M')} - "
            f"{first['summary']}"
        )

    except Exception as error:
        print(f"Calendar unavailable: {error}")
        return "Calendar temporarily unavailable"


def parse_calendar_date(value):
    """Parse common ICS date and date-time formats."""

    try:
        if "T" not in value:
            date = dt.datetime.strptime(value[:8], "%Y%m%d")
            return date.replace(tzinfo=TIMEZONE)

        if value.endswith("Z"):
            date = dt.datetime.strptime(
                value, "%Y%m%dT%H%M%SZ"
            )
            return date.replace(tzinfo=dt.timezone.utc).astimezone(
                TIMEZONE
            )

        date = dt.datetime.strptime(value, "%Y%m%dT%H%M%S")
        return date.replace(tzinfo=TIMEZONE)

    except ValueError:
        return None


def fit_text(draw, text, font, max_width):
    """Shorten long text to fit the available space."""

    text = str(text)

    while text and draw.textlength(text, font=font) > max_width:
        text = text[:-1]

    if text != str(text):
        return text + "..."

    return text


def draw_dashboard():
    """Create the final landscape PNG."""

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("L", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(image)

    now = dt.datetime.now(TIMEZONE)
    weather = get_weather()

    # Time and date.
    draw.text(
        (25, 5),
        now.strftime("%I:%M").lstrip("0"),
        font=FONT_HUGE,
        fill=BLACK,
    )

    draw.text(
        (555, 50),
        now.strftime("%p"),
        font=FONT_BIG,
        fill=GREY,
    )

    draw.text(
        (555, 120),
        now.strftime("%A"),
        font=FONT_MEDIUM,
        fill=BLACK,
    )

    draw.text(
        (555, 160),
        now.strftime("%d %b"),
        font=FONT_MEDIUM,
        fill=GREY,
    )

    draw.text(
        (555, 200),
        CITY,
        font=FONT_TINY,
        fill=GREY,
    )

    draw.line((25, 230, 775, 230), fill=BLACK, width=3)

    # Weather headings.
    draw.text((30, 245), "TODAY", font=FONT_MEDIUM, fill=BLACK)
    draw.text((420, 245), "TOMORROW", font=FONT_MEDIUM, fill=BLACK)

    # Today's weather.
    draw.text(
        (30, 285),
        f"{weather['temperature']}°C",
        font=FONT_BIG,
        fill=BLACK,
    )

    draw.text(
        (30, 345),
        fit_text(draw, weather["condition"], FONT_SMALL, 350),
        font=FONT_SMALL,
        fill=GREY,
    )

    draw.text(
        (30, 380),
        f"High {weather['today_high']}°  "
        f"Low {weather['today_low']}°",
        font=FONT_SMALL,
        fill=BLACK,
    )

    # Tomorrow's weather.
    draw.text(
        (420, 285),
        f"{weather['tomorrow_high']}°C",
        font=FONT_BIG,
        fill=BLACK,
    )

    draw.text(
        (420, 345),
        fit_text(
            draw,
            weather["tomorrow_condition"],
            FONT_SMALL,
            350,
        ),
        font=FONT_SMALL,
        fill=GREY,
    )

    draw.text(
        (420, 380),
        f"High {weather['tomorrow_high']}°  "
        f"Low {weather['tomorrow_low']}°",
        font=FONT_SMALL,
        fill=BLACK,
    )

    # Calendar section.
    draw.line((25, 430, 775, 430), fill=BLACK, width=2)

    draw.text(
        (30, 450),
        "UPCOMING",
        font=FONT_MEDIUM,
        fill=BLACK,
    )

    event = fit_text(
        draw,
        get_next_event(),
        FONT_SMALL,
        735,
    )

    draw.text(
        (30, 505),
        event,
        font=FONT_SMALL,
        fill=GREY,
    )

    # Footer.
    draw.text(
        (30, 565),
        "KINDLE DASHBOARD",
        font=FONT_TINY,
        fill=GREY,
    )

    # Save as a grayscale PNG for the Kindle.
    image.save(OUTPUT, format="PNG", optimize=True)

    print(f"Dashboard generated: {OUTPUT.resolve()}")
    print(f"Image size: {WIDTH} x {HEIGHT}")


if __name__ == "__main__":
    draw_dashboard()
```
