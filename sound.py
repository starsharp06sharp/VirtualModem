#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import audioop
import math
import queue
import struct
import sys
import wave

from common import asyncio_to_thread

try:
    import simpleaudio as sa
except:
    sa = None

NUM_CHANNELS = 1
BYTES_PER_SAMPLE = 2
SAMPLE_RATE = 8000


def sine_wave(freq, second, volume=0.3):
    amplitude = ((1 << 8 * BYTES_PER_SAMPLE - 1) - 1) * volume
    omega = 2 * math.pi * freq / SAMPLE_RATE
    num_samples = round(second * SAMPLE_RATE)
    l = []
    for i in range(num_samples):
        level = round(math.sin(omega * i) * amplitude)
        # little endian
        l.append(struct.pack('<h', level) * NUM_CHANNELS)
    return b''.join(l)


def empty_wave(second):
    num_samples = round(second * SAMPLE_RATE)
    return b'\0' * (BYTES_PER_SAMPLE * NUM_CHANNELS * num_samples)


def superposition_sine_wave(freqs, second, volume=0.3):
    assert len(freqs) > 0
    buf = sine_wave(freqs[0], second, volume)
    for freq in freqs[1:]:
        buf = audioop.add(buf, sine_wave(
            freq, second, volume), BYTES_PER_SAMPLE)
    return buf


# DTMF: Dual-Tone Multi-Frequency
#  Hz  1209 1336 1477 1633
# 697:   1    2    3    A
# 770:   4    5    6    B
# 852:   7    8    9    C
# 941:   *    0    #    D
DIGIT_TONE = {
    '1': superposition_sine_wave((697, 1209), 0.1),
    '2': superposition_sine_wave((697, 1336), 0.1),
    '3': superposition_sine_wave((697, 1477), 0.1),
    'A': superposition_sine_wave((697, 1633), 0.1),

    '4': superposition_sine_wave((770, 1209), 0.1),
    '5': superposition_sine_wave((770, 1336), 0.1),
    '6': superposition_sine_wave((770, 1477), 0.1),
    'B': superposition_sine_wave((770, 1633), 0.1),

    '7': superposition_sine_wave((852, 1209), 0.1),
    '8': superposition_sine_wave((852, 1336), 0.1),
    '9': superposition_sine_wave((852, 1477), 0.1),
    'C': superposition_sine_wave((852, 1633), 0.1),

    '*': superposition_sine_wave((941, 1209), 0.1),
    '0': superposition_sine_wave((941, 1336), 0.1),
    '#': superposition_sine_wave((941, 1477), 0.1),
    'D': superposition_sine_wave((941, 1633), 0.1),
}
DIGIT_IDLE = empty_wave(0.05)
RINGING_TONE = superposition_sine_wave((440, 480), 1)
RINGING_IDLE_SECOND = 2


if sa:
    def play_sound_blocked(buffer):
        p = sa.play_buffer(buffer, NUM_CHANNELS, BYTES_PER_SAMPLE, SAMPLE_RATE)
        p.wait_done()

    async def play_dial_tone(phone):
        global DIGIT_IDLE, DIGIT_TONE
        buffer = DIGIT_IDLE.join([DIGIT_TONE[digit]
                                  for digit in phone]) + DIGIT_IDLE
        await asyncio_to_thread(play_sound_blocked, buffer)

    async def play_ringing_tone():
        global RINGING_TONE
        buffer = RINGING_TONE
        await asyncio_to_thread(play_sound_blocked, buffer)

    BELL103_SOUND = sa.WaveObject.from_wave_file('./sound/bell103.wav')
    V22_SOUND = sa.WaveObject.from_wave_file('./sound/v22.wav')
    V32_SOUND = sa.WaveObject.from_wave_file('./sound/v32.wav')
    V34_SOUND = sa.WaveObject.from_wave_file('./sound/v34.wav')
    V90_SOUND = sa.WaveObject.from_wave_file('./sound/v90.wav')
    HANDSHAKE_SOUND = {
        300: BELL103_SOUND,
        1200: V22_SOUND,
        2400: V22_SOUND,
        4800: V32_SOUND,  # TODO: may be another sound? v.27?
        9600: V32_SOUND,
        14400: V32_SOUND,
        28800: V34_SOUND,
        33600: V34_SOUND,
        56000: V90_SOUND,
    }

    def play_handshake_sound(bps):
        global HANDSHAKE_SOUND
        try:
            wo = HANDSHAKE_SOUND[bps]
            wo.play()
        except KeyError:
            print(f'Handshake sound not found, unknown bps:{bps}')

else:
    def _empty_func(*args, **kw):
        pass

    async def _empty_await_func(*args, **kw):
        pass

    play_dial_tone = _empty_await_func
    play_ringing_tone = _empty_await_func
    play_handshake_sound = _empty_func


async def main():
    for arg in sys.argv[1:]:
        await play_dial_tone(arg)
        await play_ringing_tone()
        await asyncio.sleep(RINGING_IDLE_SECOND)
        await play_ringing_tone()
        await asyncio.sleep(RINGING_IDLE_SECOND)

    # w = wave.open('output.wav', 'wb')
    # w.setnchannels(NUM_CHANNELS)
    # w.setsampwidth(BYTES_PER_SAMPLE)
    # w.setframerate(SAMPLE_RATE)
    # w.writeframes(buffer)


if __name__ == '__main__':
    asyncio.run(main())


# python sound.py 0696675356 4646415180 2336731416 3608338160 4400826146 6253689638 8482138178 5073643399
# python sound.py 5775577 7557755 7891234
