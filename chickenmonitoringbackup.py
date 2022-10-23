### Greenhouse monitoring project ###
### July 2022 ###

import time
import alarm
import board
import ssl

import microcontroller
import socketpool
import wifi
import adafruit_minimqtt.adafruit_minimqtt as MQTT
import adafruit_bme680
import displayio
import adafruit_displayio_ssd1306
import terminalio
import adafruit_tsl2591
from adafruit_io.adafruit_io import IO_MQTT
from adafruit_display_text import label
from microcontroller import watchdog as w
from watchdog import WatchDogMode
from greenhouse_feeds import feed_names

# WiFi setup ###
try:
    from secrets import secrets
except ImportError:
    print('WiFi secrets are kept in secrets.py, please add them there!')
    raise

aio_username = secrets['aio_username']
aio_key = secrets['aio_key']
wifi.radio.connect(secrets['ssid'], secrets['password'])

# I2C
i2c = board.STEMMA_I2C()

# BME680 setup ###
bme680 = adafruit_bme680.Adafruit_BME680_I2C(i2c, debug=False)
bme680.seaLevelhPa = 1010

# TSL2591 light sensor ###
light_sensor = adafruit_tsl2591.TSL2591(i2c)

# Display Setup ###
# soft reset causes RuntimeError about too many display busses, so we hard reset
DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 64
BORDER = 5
display_bus = None
try:
    display_bus = displayio.I2CDisplay(i2c, device_address=0x3d)
except RuntimeError as e:
    print(e)
    microcontroller.reset()
display = adafruit_displayio_ssd1306.SSD1306(display_bus, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT)

# Make the display context
text_group = displayio.Group()
display.show(text_group)

# Draw a label
text_label = label.Label(terminalio.FONT, text=" " * 20, color=0xFFFFFF, x=1, y=5, scale=1)
text_group.append(text_label)

# sleep time in seconds
sleep_time = 30


# Define callback functions which will be called when certain events happen.
def connected(client):
    # Connected function will be called when the client is connected to Adafruit IO.
    # This is a good place to subscribe to feed changes.  The client parameter
    # passed to this function is the Adafruit IO MQTT client so you can make
    # calls against it easily.
    # Subscribe to changes on a feed named DemoFeed.
    client.subscribe(feed_names['sleep'])
    client.subscribe(feed_names['display'])
    client.subscribe(feed_names['sleep-time'])


def subscribe(client, userdata, topic, granted_qos):
    # This method is called when the client subscribes to a new feed.
    print('Subscribed to {0} with QOS level {1}'.format(topic, granted_qos))


def unsubscribe(client, userdata, topic, pid):
    # This method is called when the client unsubscribes from a feed.
    print('Unsubscribed from {0} with PID {1}'.format(topic, pid))


# pylint: disable=unused-argument
def disconnected(client):
    # Disconnected function will be called when the client disconnects.
    print('Disconnected from Adafruit IO!')


# pylint: disable=unused-argument
def message(client, feed_id, payload):
    # Message function will be called when a subscribed feed has a new value.
    # The feed_id parameter identifies the feed, and the payload parameter has
    # the new value.
    print('Feed {0} received new value: {1}'.format(feed_id, payload))


def on_sleep_msg(client, feed_id, payload):
    # method called whenever user/feeds/sleep has a new value
    if payload == 'AWAKE':
        print('Waking up!')
    elif payload == 'ASLEEP':
        print('***************')
        print('Going to sleep for ', sleep_time, ' seconds!')
        print('***************\n')
        time_alarm = alarm.time.TimeAlarm(monotonic_time=time.monotonic() + sleep_time)
        alarm.exit_and_deep_sleep_until_alarms(time_alarm)


def on_display_msg(client, feed_id, payload):
    if payload == 'ON':
        print('Turning display on!')
    elif payload == 'OFF':
        print('Turning display off!')


def on_set_sleep_time(client, feed_id, payload):
    print('Setting sleep time to ', payload, ' seconds')
    global sleep_time
    sleep_time = int(payload)


# Create a socket pool
pool = socketpool.SocketPool(wifi.radio)

# Initialize a new MQTT Client object
mqtt_client = MQTT.MQTT(
    broker='io.adafruit.com',
    port=1883,
    username=secrets['aio_username'],
    password=secrets['aio_key'],
    socket_pool=pool,
    ssl_context=ssl.create_default_context(),
)

# Initialize an Adafruit IO MQTT Client
io = IO_MQTT(mqtt_client)

# Connect the callback methods defined above to Adafruit IO
io.on_connect = connected
io.on_disconnect = disconnected
io.on_subscribe = subscribe
io.on_unsubscribe = unsubscribe
io.on_message = message

# register feed callbacks
io.add_feed_callback(feed_names['sleep'], on_sleep_msg)
io.add_feed_callback(feed_names['display'], on_display_msg)
io.add_feed_callback(feed_names['sleep-time'], on_set_sleep_time)

# Connect to Adafruit IO
print("Connecting to Adafruit IO...")
io.connect()
io.publish(feed_names['sleep'], 'AWAKE')  # set dashboard button to AWAKE
io.publish(feed_names['display'], 'ON')

# set sleep time to current dashboard value ###
io.get(feed_names['sleep-time'])

# Watchdog config ###
w.timeout = 10.0
w.mode = WatchDogMode.RESET
w.feed()

# environment variables ###
lastTime = 0
publishTime = 0
publishIntervalSec = 10

# Main Loop ###########################################
while True:
    w.feed()
    temperature = round((bme680.temperature * 1.8) + 32, 2)
    pressure = round(bme680.pressure, 2)
    humidity = round(bme680.humidity, 2)
    light = round(light_sensor.lux, 2)

    # Display management
    text_label.text = "Temp: " + str(temperature) \
                      + "\nHum: " + str(humidity) \
                      + "\nPress: " + str(pressure) \
                      + "\nLight: " + str(light)

    #  main sensors loop sensors
    try:
        # Explicitly pump the message loop.
        io.loop()
        # Send a new message every X seconds.
        if (time.monotonic() - publishTime) >= publishIntervalSec:
            io.publish(feed_names['temperature'], temperature)
            io.publish(feed_names['humidity'], humidity)
            io.publish(feed_names['pressure'], pressure)
            io.publish(feed_names['light'], light)

            print("Temp: " + str(temperature))
            print("Humidity: " + str(humidity))
            print("Pressure: " + str(pressure))
            print("Light: " + str(light))

            publishTime = time.monotonic()
    except (ValueError, RuntimeError) as e:
        print('Failed to get data, retrying\n', e)
        wifi.radio.connect(secrets['ssid'], secrets['password'])
        io.reconnect()
        continue

    w.feed()
