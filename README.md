# KUAL Dashboard

This is a KUAL extension that turns a Kindle shows details for an IotaWatt monitor. It will cycle between showing all sources, then an individual source. Slowly going through all the individual sources.

It is strongly based off the code from the 4DCu.be blog ([part one](http://blog.4dcu.be/diy/2020/09/27/PythonKindleDashboard_1.html),
[part two](https://blog.4dcu.be/diy/2020/10/04/PythonKindleDashboard_2.html))

## Requirements

  * A Jailbroken Kindle
  * KUAL installed with Python 3
  * If you are looking for instructions to do this, check [here](http://blog.4dcu.be/diy/2020/09/27/PythonKindleDashboard_1.html) for details and links to additional resources.

## Installation

Copy the folder `dashboard` from the repository to the `/extensions` folder on the kindle (if that folder is not there
KUAL isn't installed properly).

## Starting the Dashboard

First type `~ds` in the searchbar and hit enter. This will disable the Kindle's own deep sleep and screensaver, this is
required as this will put the device in deep sleep without the wake-up timer enabled eventually. Which in turn will
stop the dashboard from refreshing. To disable this you will need to restart the Kindle by holding the power button for
15-20 seconds and pushing restart in the menu.

Next, open KUAL and start "Dashboard IotaWatt", wait for the dashboard to appear and done!

