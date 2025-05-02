def test_sdl2_Joystick_constructor():
    import pyjoystick.sdl2

    t_name = 'Construct without initializing SDL2 first should raise RuntimeError.'
    try:
        pyjoystick.sdl2.Joystick()
        assert False, t_name
    except RuntimeError as e:
        # print('Received expected RuntimeError:', e)
        pass

    t_name = 'SDL2 init should not raise exceptions'
    try:
        pyjoystick.sdl2.init()
    except Exception as e:
        print(e)
        assert False, t_name

    t_name = 'SDL2 subsystems should be initialized after calling init()'
    assert pyjoystick.sdl2.get_init(), t_name

    t_name = 'Construct using invalid instance id should raise RuntimeError.'
    try:
        pyjoystick.sdl2.Joystick(instance_id=0)
        assert False, t_name
    except RuntimeError as e:
        # print('Received expected RuntimeError:', e)
        pass

    t_name = 'Construct using device index 0 should not throw.'
    t_note = ' This test requires a connected joystick.'
    try:
        joystick = pyjoystick.sdl2.Joystick(identifier=0)
    except RuntimeError as e:
        print(e)
        assert False, t_name + t_note

    t_name = 'Construct using device index 0 should not return null pointer.'
    assert joystick.joystick, t_name + t_note

    t_name = 'Construct using known instance id should not return null pointer.'
    joystick = pyjoystick.sdl2.Joystick(instance_id=joystick.identifier)
    assert joystick.joystick, t_name + t_note

if __name__ == '__main__':
    test_suite_name = 'test_sdl2_Joystick'

    test_sdl2_Joystick_constructor()

    print('{}: All tests finished successfully!'.format(test_suite_name))
