import os
import ctypes
import threading

from pyjoystick.utils import is_64_bit, check_os, rescale
from pyjoystick.stash import Stash
from pyjoystick.interface import Key, Joystick as BaseJoystick

# ========== SDL2 Pathing ==========
# Find SDL2 resource files properly.
from pyjoystick.sdl2_win32 import SDL2_WIN32
from pyjoystick.sdl2_win64 import SDL2_WIN64

if check_os('win') and is_64_bit():
    with SDL2_WIN64.as_file() as sdl_dll:
        os.environ.setdefault('PYSDL2_DLL_PATH', os.path.dirname(str(sdl_dll)))
        import sdl2
elif check_os('win'):
    with SDL2_WIN32.as_file() as sdl_dll:
        os.environ.setdefault('PYSDL2_DLL_PATH', os.path.dirname(str(sdl_dll)))
        import sdl2
else:
    import sdl2
# ========== END SDL2 Pathing ==========


__all__ = ['Key', 'Joystick', 'EventLoop', 'JoystickEventLoop', 'ControllerEventLoop',
           'stop_event_wait', 'run_event_loop',
           'sdl2', 'get_init', 'init', 'quit', 'key_from_event', 'joystick_key_from_event', 'controller_key_from_event',
           'get_str_mapping', 'get_mapping', 'get_mapping_name', 'get_key_mapping', 'make_str_mapping', 'set_mapping',
           'is_trigger', 'get_guid', 'rescale']


class Joystick(BaseJoystick):
    @classmethod
    def get_joysticks(cls):
        """
        Note:
            Initializes SDL2 Joystick submodule, if not already initialized.
        """
        # Check init
        if not get_init(sdl2.SDL_INIT_JOYSTICK):
            init(sdl2.SDL_INIT_JOYSTICK)

        numjoysticks = sdl2.SDL_NumJoysticks()
        # (int) Returns the number of attached joysticks on success or a negative error code on failure; call SDL_GetError() for more information.
        # Also seems to return 0 if SDL2 is not initialized.
        if numjoysticks < 0:
            raise RuntimeError("SDL_NumJoysticks() error: {}".format(sdl2.SDL_GetError()))
        return Stash(cls(identifier=i) for i in range(numjoysticks)) # Use identifier (device_index) not instance id.

    def __new__(cls, identifier=None, instance_id=None, *args, **kwargs):
        """
        identifier: device index (int) for SDL_JoystickOpen or name (str) for SDL_JoystickName
        instance_id: SDL_JoystickID (int)

        The term "device_index" identifies currently plugged in joystick devices between 0 and SDL_NumJoysticks(),
        with the exact joystick behind a device_index changing as joysticks are plugged and unplugged.
        """

        # Should never be uninitialized here since no events are received if SDL2 is not initialized -
        # unless user manually constructs Joystick.
        # SDL_INIT_JOYSTICK should always be initialized, but SDL_INIT_GAMECONTROLLER not necessarily
        if not get_init(sdl2.SDL_INIT_JOYSTICK):
            raise RuntimeError("SDL2 SDL_INIT_JOYSTICK subsystem has not been initialized")

        # Create the object
        joy = super().__new__(cls)

        # The device_index argument refers to the N'th joystick presently recognized by SDL on the system.
        # It is NOT the same as the instance ID used to identify the joystick in future events.
        # device_index should not be stored in the Joystick object because index can change at any time when adding or removing joysticks from the system.
        device_index = None

        # instance_id: SDL_JoystickID (int)
        # This is a unique ID for a joystick for the time it is connected to the system, and is never reused for the
        # lifetime of the application.
        if instance_id is not None:
            # Get the underlying joystick from the instance id (does NOT create a new one)
            # SDL_JOYDEVICEREMOVED and all other SDL_JOY#### events give the instance id
            joy.joystick = sdl2.SDL_JoystickFromInstanceID(instance_id) # Returns NULL on errors
            # print('Instance ID:', joy.joystick, sdl2.SDL_JoystickGetAttached(joy.joystick))
        else:
            # Create the underlying joystick from the enumerated identifier
            # SDL_JOYDEVICEADDED and SDL_NumJoysticks use open
            if identifier is None: # Opens the first enumerated joystick
                identifier = 0
            if isinstance(identifier, str): # identifier is joystick name
                # Get the joystick from the name or None if not found!
                for i in range(sdl2.SDL_NumJoysticks()):
                    # Open using device_index (i)
                    raw_joystick = sdl2.SDL_JoystickOpen(i) # Returns NULL on errors
                    try:
                        if sdl2.SDL_JoystickName(raw_joystick).decode('utf-8') == identifier:
                            joy.joystick = raw_joystick
                            device_index = i
                            break
                    except:
                        pass
            else: # identifier is device_index
                # Open using device_index
                device_index = identifier
                joy.joystick = sdl2.SDL_JoystickOpen(device_index) # Returns NULL on errors
            # print('ID:', raw_joystick, SDL_JoystickGetAttached(raw_joystick))
        # Check if SDL2 C-functions returned nullptr
        if not joy.joystick:
            # err = sdl2.SDL_GetError() # This does not seem to return much useful info
            # print("Create Joystick failed: {}".format(err.decode()))
            # Bail out from constructor with an exception to not return incomplete Joystick object
            raise RuntimeError("SDL_Joystick creation failed: null pointer returned")

        try:
            # joy.identifier is instance id
            joy.identifier = sdl2.SDL_JoystickInstanceID(joy.joystick)
            joy.name = sdl2.SDL_JoystickName(joy.joystick).decode('utf-8')
            joy.numaxes = sdl2.SDL_JoystickNumAxes(joy.joystick)
            joy.numbuttons = sdl2.SDL_JoystickNumButtons(joy.joystick)
            joy.numhats = sdl2.SDL_JoystickNumHats(joy.joystick)
            joy.numballs = sdl2.SDL_JoystickNumBalls(joy.joystick)
            joy.init_keys()
        except:
            pass

        # Try to get the gamepad object
        # This will only work for actual game pad devices, not for regular joysticks
        try:
            if instance_id is not None: # SDL_GameController object should already exist.
                # Instance ID should be the same as our Joystick instance ID (?) This is not clear in the docs.
                joy.gamecontroller = sdl2.SDL_GameControllerFromInstanceID(sdl2.SDL_JoystickInstanceID(joy.joystick))
            else:
                # Create new SDL_GameController instance with joystick device_index
                # SDL_GameController* SDL_GameControllerOpen(int joystick_index)
                # joystick_index is the same as the device_index passed to SDL_JoystickOpen()
                joy.gamecontroller = sdl2.SDL_GameControllerOpen(device_index)

            # Get mapping
            try:
                # Save mappings
                joy.controller_mapping = get_mapping(joy)
                joy.key_mapping = {v: k for k, v in joy.controller_mapping.items()}
                # joy.key_mapping = get_key_mapping(joy)  # Key to Name
                # joy.controller_mapping = {v: k for k, v in joy.key_mapping.items()}  # Name to key
            except:
                joy.key_mapping = {}
                joy.controller_mapping = {}
        except:
            # Joystick probably wasn't a gamepad
            joy.gamecontroller = None
            joy.key_mapping = {}
            joy.controller_mapping = {}

        try:
            joy.guid = get_guid(joy.joystick)  # Using this is more reliable for the GameController stuff
        except:
            pass

        return joy

    def is_available(self):
        """Return if this joystick is still active and available."""
        try:
            return sdl2.SDL_JoystickGetAttached(self.joystick)
            # Returns SDL_TRUE if the joystick has been opened, SDL_FALSE if it has not; call SDL_GetError() for more information.
        except:
            return False

    def close(self):
        """Close the joystick."""
        try:
            sdl2.SDL_GameControllerClose(self.gamecontroller)
        except:
            pass
        try:
            sdl2.SDL_JoystickClose(self.joystick)
        except:
            pass

# end of class Joystick(BaseJoystick)

def get_init(*subsystems):
    """Return if all the given subsystems were initialized."""
    if len(subsystems) == 0:
        subsystems = (sdl2.SDL_INIT_GAMECONTROLLER, sdl2.SDL_INIT_JOYSTICK)
    was_init = True
    for subsystem in subsystems:
        was_init = was_init and sdl2.SDL_WasInit(subsystem)
        # SDL_WasInit: Get a mask of the specified subsystems which are currently initialized.
        # (Uint32) Returns a mask of all initialized subsystems if flags is 0, otherwise it returns the initialization status of the specified subsystems.
    return was_init


def init(*subsystems):
    """Initialize the given subsystem(s).

    Note:
        SDL_INIT_GAMECONTROLLER also initializes the joystick subsystem.
    """
    if len(subsystems) == 0:
        subsystems = (sdl2.SDL_INIT_GAMECONTROLLER, sdl2.SDL_INIT_JOYSTICK)
    flags = 0
    for subsystem in subsystems:
        flags = flags | subsystem
    # Subsystem initializations are reference counted. Call SDL_QuitSubSystem as many times as you have called SDL_Init for it.
    if get_init(flags):
        sdl2.SDL_QuitSubSystem(flags)
    # int SDL_Init(Uint32 flags);
    # Uint32 flags subsystem initialization flags.
    res = sdl2.SDL_Init(flags) # Returns 0 on success or a negative error code on failure
    if res != 0:
        err = sdl2.SDL_GetError()
        raise RuntimeError("SDL_Init({}) error: {}".format(flags, err))

def quit(*subsystems):
    """Quit the given subsystem(s).

    Note:
        SDL_INIT_GAMECONTROLLER also quits the joystick subsystem.
    """
    if len(subsystems) == 0:
        # Only quit the subsystems pyjoystick is using, not everything
        subsystems = (sdl2.SDL_INIT_GAMECONTROLLER, sdl2.SDL_INIT_JOYSTICK)
    flags = 0
    for subsystem in subsystems:
        flags = flags | subsystem
    # SDL_Quit() quits all subsystems, and it doesn't take arguments. SDL_QuitSubSystem(flags) can be used to deinit a single subsystem.
    sdl2.SDL_QuitSubSystem(flags)

def get_guid(joystick):
    """Return the GUID from the given joystick object.

    Args:
        joystick (Joystick/SDL_Joystick): SDL2 joystick object

    Returns:
        guid (str): GUID String.
    """
    # If a pyjoystick Joystick was passed, get the internal SDL_Joystick
    if isinstance(joystick, BaseJoystick):
        joystick = joystick.joystick
    guid = sdl2.SDL_JoystickGetGUID(joystick)
    guid_buff = ctypes.create_string_buffer(33)
    sdl2.SDL_JoystickGetGUIDString(guid, guid_buff, ctypes.sizeof(guid_buff))
    return guid_buff.value


def get_str_mapping(joystick):
    """Return the mapping string for the joystick.

    https://wiki.libsdl.org/SDL_GameControllerAddMapping?highlight=%28%5CbCategoryGameController%5Cb%29%7C%28CategoryEnum%29

    Note:
        Hat keys have a value that is returned to make it easy to map a hat value to a function.

    Args:
        joystick (Joystick/str): Joystick object or String GUID

    Returns:
        map_str (string): The mapping string that is returned from sdl2
    """
    map_str = None

    # ===== FROM GameController =====
    if map_str is None:
        try:
            map_str = sdl2.SDL_GameControllerMapping(joystick.gamecontroller)
        except:
            try:
                map_str = sdl2.SDL_GameControllerMapping(joystick)
            except:
                pass

    # ===== FROM GUID =====
    if map_str is None:
        try:
            guid = sdl2.SDL_JoystickGetGUIDFromString(joystick.guid)
            map_str = sdl2.SDL_GameControllerMappingForGUID(guid)
        except:
            try:
                guid = sdl2.SDL_JoystickGetGUID(joystick)
                map_str = sdl2.SDL_GameControllerMappingForGUID(guid)
            except:
                pass

    if map_str is not None:
        try:
            map_str = map_str.decode('utf-8')
        except:
            pass
        return map_str
    return ''


def get_mapping(joystick):
    """Return the button mapping.

    Note:
        Hat keys have a value that is returned to make it easy to map a hat value to a function.

    Args:
        joystick (Joystick/str): Joystick object or String GUID

    Returns:
        d (dict): Dictionary of {name: Key} mappings
    """
    # Mapping dictionary
    mapping = {}
    map_str = get_str_mapping(joystick)

    for item in map_str.split(','):
        if ":" in item:
            name, key = item.split(':', 1)
            if key.startswith('b'):
                mapping[name] = Key(Key.BUTTON, int(key[1:]), joystick=joystick)
            elif key.startswith('a'):
                mapping[name] = Key(Key.AXIS, int(key[1:]), joystick=joystick)
            elif key.startswith('h'):
                key, val = key.split('.', 1)
                mapping[name] = Key(Key.HAT, int(key[1:]), value=int(val), joystick=joystick)
    return mapping


def get_mapping_name(joystick, key):
    """Return the mapping name currently associated with this key."""
    for name, k in get_mapping(joystick).items():
        if key.keytype == k.keytype and key.number == k.number:
            if key.keytype == k.HAT:  # Hat also checks for the value
                if k.value == key.value:
                    return name
            else:
                return name
    return None


def make_str_mapping(joystick, mapping):
    """Make the button mapping.
    Note:
        Hat keys should have a set value for the proper quadrant.

    Args:
        joystick (Joystick/str): Joystick object or String GUID
        mapping (dict): Dictionary of name: Key values to map to the joystick/game controller.

    Returns:
        map_str (str): String mapping to give to sdl2
    """
    # Mapping String
    guid = joystick
    name = joystick
    try:
        guid = joystick.guid.decode('utf-8')
    except (AttributeError, Exception):
        try:
            guid = sdl2.SDL_JoystickGetGUID(joystick.guid)
        except (AttributeError, Exception):
            try:
                guid = sdl2.SDL_JoystickGetGUID(joystick)
            except (AttributeError, Exception):
                pass
    try:
        name = joystick.name
    except (AttributeError, Exception):
        pass

    keys = ','.join(('{}:{}'.format(name, _key_to_mapping(key))
                     for name, key in mapping.items() if _is_key_mapping(key)))
    map_str = ','.join((str(guid), str(name), keys))
    return map_str


def set_mapping(joystick, mapping):
    """Set the button mapping.

    Note:
        Hat keys should have a set value for the proper quadrant.

    Args:
        joystick (Joystick/str): Joystick object or String GUID
        mapping (dict): Dictionary of name: Key values to map to the joystick/game controller.

    Raises:
        ValueError: If the mapping was invalid.

    Returns:
        success (int): If 1 the mapping was added. If 0 the previous mapping was updated
    """
    map_str = make_str_mapping(joystick, mapping)
    res = sdl2.SDL_GameControllerAddMapping(map_str.encode('utf-8'))
    if res == -1:
        raise ValueError('Invalid game controller mapping! Tried mapping "{}".'.format(map_str))
    return res


def _is_key_mapping(key):
    keytype = key.keytype
    return keytype == Key.BUTTON or keytype == Key.AXIS or keytype == Key.HAT


def _key_to_mapping(key):
    if key.keytype == Key.BUTTON:
        return 'b{}'.format(key.number)
    elif key.keytype == Key.AXIS:
        return 'a{}'.format(key.number)
    elif key.keytype == Key.HAT:
        return 'h{}.{}'.format(key.number, key.value)
    return None


def is_trigger(joystick, axis_id):
    """Return if the given joystick axis is a trigger (Don't want triggers scaled from -1 resting to 1).

    Args:
          joystick (SDLJoystick): Joystick object
          axis_id (int): Axis number to check

    Returns:
          is_trigger (bool): If True this axis is a trigger.
    """
    try:
        # Prioritize GameController mapping?
        if not sdl2.SDL_GameControllerGetAttached(joystick.gamecontroller):
            key_name = str(get_mapping_name(joystick, Key(Key.AXIS, axis_id))).lower()
            return 'trigger' in key_name
    except:
        pass

    # Check the left trigger
    try:
        bind = sdl2.SDL_GameControllerGetBindForAxis(joystick.gamecontroller, sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT)
        if bind.bindType == sdl2.SDL_CONTROLLER_BINDTYPE_AXIS and bind.value.axis == axis_id:
            return True
    except:
        pass

    # Check the right trigger
    try:
        bind = sdl2.SDL_GameControllerGetBindForAxis(joystick.gamecontroller, sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT)
        if bind.bindType == sdl2.SDL_CONTROLLER_BINDTYPE_AXIS and bind.value.axis == axis_id:
            return True
    except:
        pass

    try:
        return 'trigger' in str(get_mapping_name(joystick, Key(Key.AXIS, axis_id))).lower()
    except:
        pass

    return False


BIND_BTN = sdl2.SDL_CONTROLLER_BINDTYPE_BUTTON
BIND_AXS = sdl2.SDL_CONTROLLER_BINDTYPE_AXIS
MAPPING_NAMES = [
    (BIND_BTN, sdl2.SDL_CONTROLLER_BUTTON_A, 'a'),
    (BIND_BTN, sdl2.SDL_CONTROLLER_BUTTON_B, 'b'),
    (BIND_BTN, sdl2.SDL_CONTROLLER_BUTTON_X, 'x'),
    (BIND_BTN, sdl2.SDL_CONTROLLER_BUTTON_Y, 'y'),
    (BIND_BTN, sdl2.SDL_CONTROLLER_BUTTON_BACK, 'back'),
    (BIND_BTN, sdl2.SDL_CONTROLLER_BUTTON_GUIDE, 'guide'),
    (BIND_BTN, sdl2.SDL_CONTROLLER_BUTTON_START, 'start'),
    (BIND_BTN, sdl2.SDL_CONTROLLER_BUTTON_LEFTSTICK, 'leftstick'),
    (BIND_BTN, sdl2.SDL_CONTROLLER_BUTTON_RIGHTSTICK, 'rightstick'),
    (BIND_BTN, sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER, 'leftshoulder'),
    (BIND_BTN, sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER, 'rightshoulder'),
    (BIND_BTN, sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP, 'dpup'),
    (BIND_BTN, sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN, 'dpdown'),
    (BIND_BTN, sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT, 'dpleft'),
    (BIND_BTN, sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT, 'dpright'),
    (BIND_AXS, sdl2.SDL_CONTROLLER_AXIS_LEFTX, 'leftx'),
    (BIND_AXS, sdl2.SDL_CONTROLLER_AXIS_LEFTY, 'lefty'),
    (BIND_AXS, sdl2.SDL_CONTROLLER_AXIS_RIGHTX, 'rightx'),
    (BIND_AXS, sdl2.SDL_CONTROLLER_AXIS_RIGHTY, 'righty'),
    (BIND_AXS, sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT, 'lefttrigger'),
    (BIND_AXS, sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT, 'righttrigger')
    ]


def make_key_from_binding(joystick, sdl_bind_type, sdl_bind_key):
    """Return a key from the given binding."""
    if sdl_bind_type == sdl2.SDL_CONTROLLER_BINDTYPE_BUTTON:
        bind = sdl2.SDL_GameControllerGetBindForButton(joystick.gamecontroller, sdl_bind_key)
        if bind.bindType == sdl2.SDL_CONTROLLER_BINDTYPE_BUTTON:
            return Key(Key.BUTTON, bind.value.button, joystick=joystick)
        elif bind.bindType == sdl2.SDL_CONTROLLER_BINDTYPE_HAT:
            return Key(Key.HAT, bind.value.button, joystick=joystick)
        return
    elif sdl_bind_type == sdl2.SDL_CONTROLLER_BINDTYPE_BUTTON:
        bind = sdl2.SDL_GameControllerGetBindForAxis(joystick.gamecontroller, sdl_bind_key)
        return Key(Key.AXIS, bind.value.button, joystick=joystick)


def get_key_mapping(joystick):
    """Return a dictionary mapping a key to a controller button/axis name."""
    mapping = {}
    for bind_type, bind_key, name in MAPPING_NAMES:
        key = make_key_from_binding(joystick, bind_type, bind_key)
        if key is not None:
            mapping[key] = name
    return mapping


def joystick_key_from_event(event, joystick=None):
    """Every library type should implement a key_from_event function to convert an event into a key.

    Args:
        event (SDL_Event): Event that occurred
        joystick (Joystick)[None]: Joystick object

    Returns:
        key (Key)[None]: Key created from the event.
    """
    if joystick is None:
        try:
            joystick = Joystick(instance_id=event.jdevice.which)
        except (ValueError, TypeError, Exception):
            return None

    # Joystick Events
    if event.type == sdl2.SDL_JOYBUTTONDOWN:
        key = Key(Key.BUTTON, event.jbutton.button, 1, joystick)
    elif event.type == sdl2.SDL_JOYBUTTONUP:
        key = Key(Key.BUTTON, event.jbutton.button, 0, joystick)
    elif event.type == sdl2.SDL_JOYAXISMOTION:
        value = event.jaxis.value
        if is_trigger(joystick, event.jaxis.axis):
            value = rescale(value, -32768, 32767, 0, 1)  # Make triggers rest at 0
        else:
            value = rescale(value, -32768, 32767, -1, 1)
        key = Key(Key.AXIS, event.jaxis.axis, value, joystick)
    elif event.type == sdl2.SDL_JOYHATMOTION:
        key = Key(Key.HAT, event.jhat.hat, event.jhat.value, joystick)
    elif event.type == sdl2.SDL_JOYBALLMOTION:
        # WIP (NOT TESTED)
        key = Key(Key.BALL, event.jball.ball, event.jball.value, joystick)
    else:
        return

    key.controller_key_name = joystick.key_mapping.get(key, None)
    return key


key_from_event = joystick_key_from_event


def controller_key_from_event(event, joystick=None):
    """Every library type should implement a key_from_event function to convert an event into a key.

    Args:
        event (SDL_Event): Event that occurred
        joystick (Joystick)[None]: Joystick object

    Returns:
        key (Key)[None]: Key created from the event. Attribute 'controller_key_name' matches the controller mapping
    """
    if joystick is None:
        try:
            joystick = Joystick(instance_id=event.cdevice.which)
        except (ValueError, TypeError, Exception):
            return None

    # Gamepad
    if event.type == sdl2.SDL_CONTROLLERBUTTONDOWN:
        if event.cbutton.button == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
            key = Key(Key.HAT, 0, Key.HAT_UP, joystick)
        elif event.cbutton.button == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
            key = Key(Key.HAT, 0, Key.HAT_DOWN, joystick)
        elif event.cbutton.button == sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT:
            key = Key(Key.HAT, 0, Key.HAT_LEFT, joystick)
        elif event.cbutton.button == sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
            key = Key(Key.HAT, 0, Key.HAT_RIGHT, joystick)
        else:
            key = Key(Key.BUTTON, event.cbutton.button, 1, joystick)
    elif event.type == sdl2.SDL_CONTROLLERBUTTONUP:
        if event.cbutton.button == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
            key = Key(Key.HAT, 0, Key.HAT_UP, joystick)
        elif event.cbutton.button == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
            key = Key(Key.HAT, 0, Key.HAT_DOWN, joystick)
        elif event.cbutton.button == sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT:
            key = Key(Key.HAT, 0, Key.HAT_LEFT, joystick)
        elif event.cbutton.button == sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
            key = Key(Key.HAT, 0, Key.HAT_RIGHT, joystick)
        else:
            key = Key(Key.BUTTON, event.cbutton.button, 0, joystick)
    elif event.type == sdl2.SDL_CONTROLLERAXISMOTION:
        value = event.caxis.value
        if is_trigger(joystick, event.caxis.axis):
            value = rescale(value, -32768, 32767, 0, 1)  # Make triggers rest at 0
        else:
            value = rescale(value, -32768, 32767, -1, 1)
        key = Key(Key.AXIS, event.caxis.axis, value, joystick)
    else:
        return

    key.controller_key_name = joystick.key_mapping.get(key, None)
    return key


def stop_event_wait():
    """Post an event to break out of the event loop wait."""
    try:
        user_event = sdl2.SDL_Event()
        user_event.type = sdl2.SDL_USEREVENT
        user_event.user.code = 2
        user_event.user.data1 = None
        user_event.user.data2 = None
        sdl2.SDL_PushEvent(ctypes.byref(user_event))
    except:
        pass


class EventLoop:
    """
    This can be used as an iterator or by registering functions to event types and calling `run()`.

    .. code-block:: python

        for event in EventLoop(alive, sdl2.SDL_Event()):
            # Check the event
            if event.type == sdl2.SDL_JOYDEVICEADDED:
                try:
                    # NOTE: event.jdevice.which is the id to use for SDL_JoystickOpen()
                    joy = Joystick(identifier=event.jdevice.which)
                    add_joystick(joy)
                except:
                    pass
            elif event.type == sdl2.SDL_JOYDEVICEREMOVED:
                try:
                    # NOTE: event.jdevice.which is the id to use for SDL_JoystickFromInstanceID()
                    joy = Joystick(instance_id=event.jdevice.which)
                    remove_joystick(joy)
                except:
                    pass
            else:
                # NOTE: event.jdevice.which is the id to use for SDL_JoystickFromInstanceID()
                joy = Joystick(instance_id=event.jdevice.which)
                key = key_from_event(event, joy)
                if key is not None:
                    handle_key_event(key)
    """
    def __init__(self, alive=None, event=None, timeout=2000, **kwargs):
        """Initialize the event loop.

        Args:
            alive (function/threading.Event)[None]: Function that returns True to keep running or threading.Event that
                is alive when set.
            event (sdl2.SDL_Event)[None]: Event object memory to continually populate with new events.
            timeout (int)[2000]: Milliseconds to wait for an event.
        """
        if alive is None:
            alive = threading.Event()
            alive.set()
        if event is None:
            event = sdl2.SDL_Event()
        self.alive = alive
        self.event = event
        self.timeout = timeout

        self.event_handler = {}

        # Save kwargs
        for k, v in kwargs.items():
            try:
                setattr(self, k, v)
            except (TypeError, ValueError, Exception):
                pass

    def register(self, event_type, func=None):
        """Decorator to register a function to handle a specific event type.

        Args:
            event_type (sdl2.SDL_JOYDEVICEEVENT): Type of event to call this function for. None if no other event types
                handle the event.
            func (function/callable)[None]: Function that takes in an event. If None return a decorator function.

        Returns:
            func (function/callable): Returns a decorator function if the given func was None or returns the given func.
        """
        if func is None:
            def decorator(func):
                return self.register(event_type, func)
            return decorator

        self.event_handler[event_type] = func
        return func

    def unregister(self, event_type):
        """Stop handling an event type."""
        try:
            del self.event_handler[event_type]
        except (KeyError, TypeError, Exception):
            pass

    def call_event(self, event):
        """Call the given event with the registered event type function."""
        # If event.type not registered try None as a general event handler.
        func = self.event_handler.get(event.type, self.event_handler.get(None, None))
        if callable(func):
            return func(event)

    def start(self):
        """Run the event loop."""
        self.run()

    def stop(self):
        """Try to stop running the event loop."""
        if isinstance(self.alive, threading.Event):
            self.alive.clear()
        try:
            stop_event_wait()
        except (AttributeError, Exception):
            pass

    def run(self):
        """Run the event loop."""
        # Check type because alive can be threading.Event or function
        if isinstance(self.alive, threading.Event):
            self.alive.set()

        for event in self:
            self.call_event(event)

    def is_alive(self):
        """Return if this event loop is alive and should keep running."""
        if isinstance(self.alive, threading.Event):
            return self.alive.is_set()  # If a threading event
        if callable(self.alive):
            return self.alive()
        raise TypeError("Invalid type for alive")

    def __iter__(self):
        """Return this object as an iterator for use with the for loop or next()"""
        return self

    def __next__(self):
        """Wait and return the next event found."""
        while self.is_alive():
            # Wait for an event
            if sdl2.SDL_WaitEventTimeout(ctypes.byref(self.event), self.timeout) != 0:
                return self.event  # If the event was successful return the event

        # If not alive raise stop
        raise StopIteration


class JoystickEventLoop(EventLoop):

    default_key_from_event = staticmethod(joystick_key_from_event)

    def __init__(self, add=None, remove=None, handle_key=None, key_from_event=None,
                 alive=None, event=None, timeout=2000, **kwargs):
        """Initialize the event loop.
        Note:
            Also initializes SDL2 Joystick submodule, if not already initialized.

        Args:
            add (function/callable)[None]: Function that takes in a joystick on a SDL_JOYDEVICEADDED event.
            remove (function/callable)[None]: Function that takes in a joystick on a SDL_JOYDEVICEREMOVED event.
            handle_key (function/callable)[None]: Function that takes in Key when other events occur.
            key_from_event (function/callable)[None]: Function that takes an event and
                turns it into a Key if possible.
            alive (function/threading.Event)[None]: Function that returns True to keep running or threading.Event that
                is alive when set.
            event (sdl2.SDL_Event)[None]: Event object memory to continually populate with new events.
            timeout (int)[2000]: Milliseconds to wait for an event.
        """
        if key_from_event is None:
            key_from_event = self.default_key_from_event
        super().__init__(alive, event, timeout, **kwargs)

        # Set callback functions
        self.add = add
        self.remove = remove
        self.handle_key = handle_key
        self.key_from_event = key_from_event

        # Register base events
        self.register(sdl2.SDL_JOYDEVICEADDED, self.on_add)
        self.register(sdl2.SDL_JOYDEVICEREMOVED, self.on_remove)
        self.register(None, self.on_key_event)  # Every other event

        # Init SDL Joystick
        # Init only Joystick is enough because gamepads are both joysticks and controllers
        if not get_init(sdl2.SDL_INIT_JOYSTICK):
            init(sdl2.SDL_INIT_JOYSTICK)

    def get_joystick(self, event):
        """Return the joystick for this event"""
        # NOTE: event.jdevice.which needs careful categorisation because device index is not at all compatible with instance id
        # struct SDL_JoyDeviceEvent
        # Sint32 which;       /**< The joystick device index for the ADDED event, instance id for the REMOVED event */
        # For on_add() identifier = device index
        if event.type == sdl2.SDL_JOYDEVICEADDED:
            # print("JS get_joystick SDL_JOYDEVICEADDED")
            return Joystick(identifier=event.jdevice.which)
        if event.type == sdl2.SDL_CONTROLLERDEVICEADDED:
            # print("JS get_joystick SDL_CONTROLLERDEVICEADDED")
            return Joystick(identifier=event.jdevice.which)
        # For all other joystick events instance_id = instance id
        # SDL_JoystickID which; /**< The joystick instance id */
        return Joystick(instance_id=event.jdevice.which)

    # This will be called 2x: once for Joystick and once for GameController if both SDL subsystems are initialized
    # Joysticks that are supported game controllers receive both an SDL_JoyDeviceEvent and an SDL_ControllerDeviceEvent.
    # ControllerEventLoop does not implement its own on_add
    def on_add(self, event):
        assert event.type == sdl2.SDL_JOYDEVICEADDED or event.type == sdl2.SDL_CONTROLLERDEVICEADDED, \
            "on_add event.type should be SDL_JOYDEVICEADDED or SDL_CONTROLLERDEVICEADDED"
        joy = None
        try:
            # Joystick instance is created inside get_joystick
            joy = self.get_joystick(event)
        except:
            pass
        if joy and callable(self.add):
            self.add(joy)

    # This will be called 2x: once for Joystick and once for GameController if both SDL subsystems are initialized
    # Joysticks that are supported game controllers receive both an SDL_JoyDeviceEvent and an SDL_ControllerDeviceEvent.
    # ControllerEventLoop does not implement its own on_remove
    def on_remove(self, event):
        assert event.type == sdl2.SDL_JOYDEVICEREMOVED or event.type == sdl2.SDL_CONTROLLERDEVICEREMOVED, \
            "on_remove event.type should be SDL_JOYDEVICEREMOVED or SDL_CONTROLLERDEVICEREMOVED"
        joy = None
        try:
            joy = self.get_joystick(event)
        except:
            pass
        if joy and callable(self.remove):
            self.remove(joy)

    # Joysticks that are supported game controllers receive both an SDL_JoyDeviceEvent and an SDL_ControllerDeviceEvent.
    # ControllerEventLoop does not implement its own on_key_event
    def on_key_event(self, event):
        key = self.key_from_event(event, self.get_joystick(event))
        if key is not None and callable(self.handle_key):
            self.handle_key(key)


class ControllerEventLoop(JoystickEventLoop):

    default_key_from_event = staticmethod(controller_key_from_event)

    def __init__(self, add=None, remove=None, handle_key=None, key_from_event=None,
                 alive=None, event=None, timeout=2000, **kwargs):
        """Initialize the event loop.
        Note:
            Also initializes SDL2 GameController submodule, if not already initialized.

        Args:
            add (function/callable)[None]: Function that takes in a joystick on a SDL_JOYDEVICEADDED event.
            remove (function/callable)[None]: Function that takes in a joystick on a SDL_JOYDEVICEREMOVED event.
            handle_key (function/callable)[None]: Function that takes in Key when other events occur.
            key_from_event (function/callable)[None]: Function that takes an event and
                turns it into a Key if possible.
            alive (threading.Event/function/callable)[None]: threading.Event that is alive when set or function that
                returns True to keep running.
            event (sdl2.SDL_Event)[None]: Event object memory to continually populate with new events.
            timeout (int)[2000]: Milliseconds to wait for an event.
        """
        super().__init__(add=add, remove=remove, handle_key=handle_key, key_from_event=key_from_event,
                         alive=alive, event=event, timeout=timeout, **kwargs)

        # Register base events
        self.register(sdl2.SDL_CONTROLLERDEVICEREMAPPED, self.on_mapped)

        # Init SDL GameController
        # Initializing GameController inits both GameController and Joystick subsystems
        if not get_init(sdl2.SDL_INIT_GAMECONTROLLER):
            init(sdl2.SDL_INIT_GAMECONTROLLER)

    def get_joystick(self, event):
        """Return the joystick for this event"""
        # NOTE: event.cdevice.which needs careful categorisation because device index is not at all compatible with instance id
        # struct SDL_ControllerDeviceEvent
        # Sint32 which; /**< The joystick device index for the ADDED event, instance id for the REMOVED or REMAPPED event */
        # For on_add() identifier = device index
        if event.type == sdl2.SDL_JOYDEVICEADDED:
            # print("GC get_joystick SDL_JOYDEVICEADDED")
            return Joystick(identifier=event.jdevice.which)
        if event.type == sdl2.SDL_CONTROLLERDEVICEADDED:
            # print("GC get_joystick SDL_CONTROLLERDEVICEADDED")
            return Joystick(identifier=event.cdevice.which)
        # For all other joystick and gamecontroller events instance_id = instance id
        # SDL_JoystickID which; /**< The joystick instance id */
        return Joystick(instance_id=event.cdevice.which)

    def on_mapped(self, event):
        try:
            # Save mappings
            joy = self.get_joystick(event)
            joy.controller_mapping = get_mapping(joy)
            joy.key_mapping = {v: k for k, v in joy.controller_mapping.items()}
        except:
            pass


def run_event_loop(add_joystick, remove_joystick, handle_key_event, alive=None, key_from_event=None, **kwargs):
    """Run the an event loop to process SDL Events.

    Args:
        add_joystick (callable/function): Called when a new Joystick is found!
        remove_joystick (callable/function): Called when a Joystick is removed!
        handle_key_event (callable/function): Called when a new key event occurs!
        alive (callable/function)[None]: Function to return True to continue running. If None run forever
        key_from_event (callable/function)[None]: Take in event, joystick and return a key or None for the event.
    """
    event_loop = JoystickEventLoop(add_joystick, remove_joystick, handle_key_event,
                                   alive=alive, key_from_event=key_from_event, **kwargs)
    event_loop.run()


# Attach a way to stop waiting by posting an event
run_event_loop.stop_event_wait = stop_event_wait
