import time
import alarm
import board
import ssl
import socketpool
import wifi
import adafruit_minimqtt.adafruit_minimqtt as MQTT
import adafruit_bme680
from random import randint
from adafruit_io.adafruit_io import IO_MQTT
from adafruit_seesaw import seesaw, rotaryio, digitalio

### WiFi setup ###
try:
    from secrets import secrets
except ImportError:
    print('WiFi secrets are kept in secrets.py, please add them there!')
    raise

aio_username = secrets['aio_username']
aio_key = secrets['aio_key']
wifi.radio.connect(secrets['ssid'], secrets['password'])

### I2C
i2c = board.STEMMA_I2C()

### BME680 setup ###
bme680 = adafruit_bme680.Adafruit_BME680_I2C(i2c, debug=False)
bme680.seaLevelhPa = 1010

### Rotary encoder setup
seesaw1 = seesaw.Seesaw(i2c, addr=0x36)
seesaw2 = seesaw.Seesaw(i2c, addr=0x37)
seesaw_product = (seesaw1.get_version() >> 16) & 0xFFFF
print("Found product {}".format(seesaw_product))
if seesaw_product != 4991:
    print("Wrong firmware loaded?  Expected 4991")
seesaw_product = (seesaw2.get_version() >> 16) & 0xFFFF
print("Found product {}".format(seesaw_product))
if seesaw_product != 4991:
    print("Wrong firmware loaded?  Expected 4991")

seesaw1.pin_mode(24, seesaw1.INPUT_PULLUP)
seesaw2.pin_mode(24, seesaw2.INPUT_PULLUP)
button1 = digitalio.DigitalIO(seesaw1, 24)
button2 = digitalio.DigitalIO(seesaw2, 24)
button_held1 = False
button_held2 = False

encoder1 = rotaryio.IncrementalEncoder(seesaw1)
encoder2 = rotaryio.IncrementalEncoder(seesaw2)
last_enc1_position = None
last_enc2_position = None

### sleep time in seconds
sleep_time = 30

# Define callback functions which will be called when certain events happen.
def connected(client):
    # Connected function will be called when the client is connected to Adafruit IO.
    # This is a good place to subscribe to feed changes.  The client parameter
    # passed to this function is the Adafruit IO MQTT client so you can make
    # calls against it easily.
    # Subscribe to changes on a feed named DemoFeed.
    client.subscribe('sleep')
    client.subscribe('textmsg')


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
    if payload == '1':
        print('Waking up!')
    elif payload == '0':
        print('***************')
        print('Going to sleep for ', sleep_time, ' seconds!')
        print('***************\n')
        time_alarm = alarm.time.TimeAlarm(monotonic_time=time.monotonic() + sleep_time)
        alarm.exit_and_deep_sleep_until_alarms(time_alarm)

def on_text_msg(client, feed_id, payload):
    print('Received text message :', payload)

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
#io.add_feed_callback('textmsg', on_text_msg)
io.add_feed_callback('textmsg', on_set_sleep_time)
io.add_feed_callback('sleep', on_sleep_msg)

# Connect to Adafruit IO
print("Connecting to Adafruit IO...")
io.connect()
io.publish('sleep', 1)  # set dashboard button to AWAKE
io.publish('textmsg', 30)

### main loop ###
lastTime = 0
while True:
    # rotary encoder
    # negate the position to make clockwise rotation positive
    position1 = -encoder1.position
    position2 = -encoder2.position

    # encoder 1 ##############################
    if position1 != last_enc1_position:
        last_enc1_position = position1

        if (position1 < 0):
            position1 = 0
        elif (position1 > 100):
            position1 = 100
        print("Position 1: {}".format(position1))

    if not button1.value and not button_held1:
        button_held1 = True
        print("Button 1 pressed")

    if button1.value and button_held1:
        button_held1 = False
        print("Button 1 released")

    # encoder 2 ##############################
    if position2 != last_enc2_position:
        last_enc2_position = position2

        if (position2 < 0):
            position2 = 0
        elif (position2 > 100):
            position2 = 100
        print("Position 2: {}".format(position2))

    if not button2.value and not button_held2:
        button_held2 = True
        print("Button 2 pressed")

    if button2.value and button_held2:
        button_held2 = False
        print("Button 2 released")


    #  sensors
    try:
        # Explicitly pump the message loop.
        io.loop()
        # Send a new message every 10 seconds.
        if (time.monotonic() - lastTime) >= 10:
            value = randint(0, 1000)
            io.publish('temperature', (bme680.temperature * 1.8) + 32)
            io.publish('humidity', bme680.humidity)
            io.publish('pressure', bme680.pressure)
            io.publish('gas', bme680.gas)

            io.publish('rotaryencoder1', position1)
            io.publish('rotaryencoder2', position2)

            lastTime = time.monotonic()
    except (ValueError, RuntimeError) as e:
        print('Failed to get data, retrying\n', e)
        wifi.radio.connect(secrets['ssid'], secrets['password'])
        io.reconnect()
        continue

