#! /usr/bin/env python3

import json
import os
import random
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request
import urllib.parse

from dataclasses import dataclass
from functools import lru_cache
from math import log
from typing import Any, Optional
from xml.etree.ElementTree import Element, SubElement, tostring

# IoTaWatt device API URL (Change this to match your device IP)
# IOTAWATT_ADDRESS = "http://iotawatt.local"
IOTAWATT_ADDRESS = "http://192.168.128.5"
LOGARITHMIC = False


@dataclass
class Region:
    min_x: float
    min_y: float
    max_x: float
    max_y: float


def get(query: str, params: dict[str, Any]):
    url = f"{IOTAWATT_ADDRESS}/{query}"
    if params:
        query_str = urllib.parse.urlencode(params)
        url = f"{url}?{query_str}"

    with urllib.request.urlopen(url) as response:
        return json.loads(response.read())


def get_iotawatt_sensor_data() -> dict[str, list[tuple[float, float]]]:
    series = get("query", {"show": "series"})

    params = {
        # Last 24 hours
        "begin": "s-24h",
        # Until now
        "end": "s",
        "group": "auto",
        "format": "json",
        "resolution": "high",
        "header": "yes",
    }

    sources = [f"{x['name']}.Watts.d1" for x in series["series"] if x["unit"] == "Watts"]
    params["select"] = "[time.utc.unix," + ",".join(sources) + "]"

    sensor_data = get("query", params)

    return convert_sensor_data(sensor_data)


def normalise(value: float, min_val: float, max_val: float, new_min: float, new_max: float) -> float:
    """Scale value from one range to another."""
    return new_min + (value - min_val) * (new_max - new_min) / (max_val - min_val)


def scale_y(value: float) -> float:
    if LOGARITHMIC:
        return log(value)
    return value


# List of sensors each reporting a list of (time, value) points
def convert_sensor_data(data: dict[str, Any]) -> dict[str, list[tuple[float, float]]]:
    label: list[str] = data["labels"]
    sensor_data: list[list[float]] = data["data"]

    # Check
    if label[0] != "Time":
        raise Exception("Time not first element")

    first_len = len(sensor_data[0])
    if all(len(sublist) == first_len for sublist in sensor_data) is False:
        raise Exception("Data not all at the same length")

    points: list[list[tuple[float, float]]] = []
    for i in range(1, len(sensor_data[0])):
        plist: list[tuple[float, float]] = []
        for p in sensor_data:
            x = p[0]
            y = scale_y(p[i])
            plist.append((x, y))
        points.append(plist)

    return {a: b for a, b in zip(label[1:], points)}


def get_data_region(data: dict[str, list[tuple[float, float]]]):
    all_points = [point for points in data.values() for point in points]
    return Region(
        min_x=min(x for x, _ in all_points),
        max_x=max(x for x, _ in all_points),
        min_y=min(y for _, y in all_points),
        max_y=max(y for _, y in all_points),
    )


def normalise_data(
    data: dict[str, list[tuple[float, float]]],
    data_region: Region,
    draw_region: Region,
) -> dict[str, list[tuple[float, float]]]:
    return {
        key: [
            (
                normalise(
                    x,
                    data_region.min_x,
                    data_region.max_x,
                    draw_region.min_x,
                    draw_region.max_x,
                ),
                normalise(
                    y,
                    data_region.min_y,
                    data_region.max_y,
                    draw_region.min_y,
                    draw_region.max_y,
                ),
            )
            for x, y in points
        ]
        for key, points in data.items()
    }


# Generate an SVG graph
def generate_svg(
    data: dict[str, Any],
    width: int = 1448,
    height: int = 1072,
    padding: int = 50,
    invert: Optional[bool] = None,
    highlight_power: float = 1000,
    invert_highlight: Optional[bool] = None,
    only_source: Optional[str] = None,
    normalise_before_filter: bool = True,
    rotate: bool = True,
):
    if invert is None:
        invert = random.choice([True, False])
    if invert_highlight is None:
        invert_highlight = random.choice([True, False])

    foreground = "white" if invert else "black"
    background = "black" if invert else "white"

    if only_source is not None and only_source not in data:
        print(f"Ignoring request to filter non-existent field: {only_source}")
        only_source = None

    if only_source and normalise_before_filter is False:
        data = {only_source: data[only_source]}

    data_region = get_data_region(data)

    draw_region = Region(
        min_x=padding,
        max_x=width - padding,
        min_y=padding,
        max_y=height - padding,
    )

    # Draw a rectangle that identifies the 1kw+ region
    y_highlight = normalise(
        scale_y(highlight_power),
        data_region.min_y,
        data_region.max_y,
        draw_region.min_y,
        draw_region.max_y,
    )
    data = normalise_data(data, data_region, draw_region)

    if only_source and normalise_before_filter is True:
        data = {only_source: data[only_source]}

    svg = Element("svg", width=str(width), height=str(height), xmlns="http://www.w3.org/2000/svg")
    group = SubElement(svg, "g")
    if rotate:
        group.set("transform", f"translate(0, {width}) rotate(-90)")
        svg.attrib["width"] = str(height)
        svg.attrib["height"] = str(width)

    SubElement(group, "rect", width=str(width), height=str(height), fill=background)

    if invert_highlight:
        # For "inversion" color the other half of the region instead
        SubElement(
            group,
            "rect",
            x=str(draw_region.min_x),
            y=str(height - y_highlight),
            width=str(draw_region.max_x - draw_region.min_x),
            height=str(y_highlight - draw_region.min_y),
            fill="grey",
        )
    else:
        SubElement(
            group,
            "rect",
            x=str(draw_region.min_x),
            y=str(draw_region.min_y),
            width=str(draw_region.max_x - draw_region.min_x),
            height=str(draw_region.max_y - y_highlight),
            fill="grey",
        )

    title = SubElement(
        group,
        "text",
        x="0",
        y="0",
        fill=foreground,
        transform=f"translate({width / 2 - 200}, {padding / 2 + 10}) scale(2)",
    )
    if only_source is None:
        title.text = "Power consumption"
    else:
        title.text = f"Power consumption ({only_source})"

    # X Axis
    SubElement(
        group,
        "line",
        x1=str(padding),
        y1=str(height - padding),
        x2=str(width - padding),
        y2=str(height - padding),
        stroke=foreground,
    )
    # X-axis label
    xlabel = SubElement(
        group,
        "text",
        x="0",
        y="0",
        fill=foreground,
        transform=f"translate({width / 2 - 120}, {height - padding / 2 + 10}) scale(2)",
    )
    xlabel.text = "Time (Previous 24 hours)"

    # Y Axis
    SubElement(
        group,
        "line",
        x1=str(padding),
        y1=str(padding),
        x2=str(padding),
        y2=str(height - padding),
        stroke=foreground,
    )
    # Y-axis label (Rotated)
    ylabel = SubElement(
        group,
        "text",
        x="0",
        y="0",
        font_size="12",
        fill=foreground,
        transform=f"translate({padding / 2 + 10}, {height / 2 + 100}) scale(2) rotate(-90)",
    )
    if LOGARITHMIC:
        ylabel.text = f"Power (Logarithmic. Higher region {highlight_power}W)"
    else:
        ylabel.text = f"Power (Higher region {highlight_power}W)"

    for source in data:
        points_str = [f"{x[0]:0.2f},{(height - x[1]):0.2f}" for x in data[source]]
        SubElement(group, "polyline", points=" ".join(points_str), stroke=foreground, fill="none", stroke_width="2")

    return tostring(svg).decode()


def generate_files(output_dir: str):
    data = get_iotawatt_sensor_data()

    # Shows all the sources
    # print(data.keys())

    shutil.rmtree(output_dir, ignore_errors=True)
    os.makedirs(output_dir, exist_ok=True)

    base_name = f"{output_dir}/all"
    svg_file = f"{base_name}.svg"
    png_file = f"{base_name}.png"
    with open(svg_file, "w") as f:
        f.write(generate_svg(data))
    convert_svg_to_png(svg_file, png_file)

    for source in data:
        base_name = f"{output_dir}/source_{source}"
        svg_file = f"{base_name}.svg"
        png_file = f"{base_name}.png"

        with open(svg_file, "w") as f:
            f.write(generate_svg(data, only_source=source))
        convert_svg_to_png(svg_file, png_file)


def convert_svg_to_png(svg_file: str, png_file: str):
    if os.path.exists("/tmp/rsvg-convert-lib") is False:
        source = get_script_dir() + "/../external/rsvg-convert-lib"
        dest = "/tmp/rsvg-convert-lib"
        shutil.copytree(source, dest)

    subprocess.run(
        [
            "/tmp/rsvg-convert-lib/rsvg-convert",
            "-o",
            png_file,
            svg_file,
        ]
    )


@lru_cache
def get_script_dir():
    script_path = os.path.abspath(__file__)
    return os.path.dirname(script_path)


def display_files(output_dir: str):
    for root, _dirs, files in os.walk(output_dir):
        for f in files:
            if f.endswith(".png") and f != "all.png":
                display_file(f"{root}all.png")
                sleep(15)
                display_file(f"{root}{f}")
                sleep(15)


def sleep(duration: int):
    # Having this actually sleep is painful
    # So.. don't - and externally power it instead
    if False:
        time.sleep(2)
        with open("/sys/class/rtc/rtc1/wakealarm", "w") as f:
            pass

        # Following line contains sleep time in seconds
        with open("/sys/class/rtc/rtc1/wakealarm", "w") as f:
            f.write(f"+{duration - 2}")

        # Following line will put device into deep sleep until the alarm above is triggered
        with open("/sys/power/state", "w") as f:
            f.write("mem")
    else:
        time.sleep(duration)


def display_file(filename: str):
    print(f"Displaying {filename}")
    # subprocess.run(["fbink", "-c", "-h"])
    subprocess.run(
        [
            "fbink",
            "-c",
            "-g",
            f"file={filename},w=1072,halign=center,valign=center",
        ]
    )


def set_brightness(level: int):
    for subdir in os.listdir("/sys/class/backlight"):
        brightness = f"/sys/class/backlight/{subdir}/brightness"
        print(brightness)
        if os.path.exists(brightness):
            print(f"Setting brightness to {level}")
            with open(brightness, "w") as f:
                f.write(str(level))


def main():
    try:
        subprocess.run(["/usr/bin/lipc-set-prop", "com.lab126.powerd", "preventScreenSaver", "1"])
        subprocess.run(["/usr/bin/lipc-set-prop", "com.lab126.deviced", "enable_touch", "0"])
        set_brightness(0)
        print("Starting")

        while True:
            output_dir = "/tmp/iotawatt/"
            generate_files(output_dir)

            display_files(output_dir)

            if len(sys.argv) > 1:
                break
    except Exception:
        subprocess.run(["fbink", "-c"])
        error_message = traceback.format_exc()
        for i, line in enumerate(error_message.split("\n")):
            line = line.replace(get_script_dir() + "/", "")
            subprocess.run(["fbink", "-x", "1", "-y", str(i + 1), line])
        raise
    finally:
        subprocess.run(["/usr/bin/lipc-set-prop", "com.lab126.powerd", "preventScreenSaver", "0"])
        subprocess.run(["/usr/bin/lipc-set-prop", "com.lab126.deviced", "enable_touch", "1"])
        set_brightness(255)


if __name__ == "__main__":
    main()
