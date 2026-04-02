#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import math
import sys

from pydub import AudioSegment
from pydub.generators import Sine
from pydub.playback import play as pydub_play

from common import asyncio_to_thread

NUM_CHANNELS = 1
BYTES_PER_SAMPLE = 2
SAMPLE_RATE = 8000


def empty_wave(second) -> AudioSegment:
    return AudioSegment.silent(
        duration=round(second * 1000), frame_rate=SAMPLE_RATE
    ).set_channels(NUM_CHANNELS).set_sample_width(BYTES_PER_SAMPLE)


def superposition_sine_wave(freqs, second, volume=0.3):
    assert len(freqs) > 0
    duration_ms = round(second * 1000)
    if volume <= 0:
        return empty_wave(second)

    gain_db = 20 * math.log10(volume)
    segment = Sine(freqs[0], sample_rate=SAMPLE_RATE).to_audio_segment(
        duration=duration_ms,
        volume=gain_db,
    )
    segment = segment.set_channels(NUM_CHANNELS).set_sample_width(BYTES_PER_SAMPLE)

    for freq in freqs[1:]:
        tone = Sine(freq, sample_rate=SAMPLE_RATE).to_audio_segment(
            duration=duration_ms,
            volume=gain_db,
        )
        tone = tone.set_channels(NUM_CHANNELS).set_sample_width(BYTES_PER_SAMPLE)
        segment = segment.overlay(tone)

    return segment


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

    '-': empty_wave(0.1),
    ' ': empty_wave(0.1),
}
DIGIT_IDLE = empty_wave(0.05)
RINGING_TONE = superposition_sine_wave((440, 480), 1)
RINGING_IDLE_SECOND = 2


def play_sound_blocked(segment: AudioSegment):
    pydub_play(segment)


async def play_dial_tone(phone):
    segments = []
    for digit in phone:
        segments.append(DIGIT_TONE[digit])
        segments.append(DIGIT_IDLE)
    buffer = sum(segments, AudioSegment.empty())
    await asyncio_to_thread(play_sound_blocked, buffer)


async def play_ringing_tone():
    await asyncio_to_thread(play_sound_blocked, RINGING_TONE)


BELL103_SOUND = AudioSegment.from_wav('./sound/bell103.wav')
V22_SOUND = AudioSegment.from_wav('./sound/v22.wav')
V32_SOUND = AudioSegment.from_wav('./sound/v32.wav')
V34_SOUND = AudioSegment.from_wav('./sound/v34.wav')
V90_SOUND = AudioSegment.from_wav('./sound/v90.wav')
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


async def play_handshake_sound(bps):
    global HANDSHAKE_SOUND
    try:
        segment = HANDSHAKE_SOUND[bps]
    except KeyError:
        print(f'Handshake sound not found, unknown bps:{bps}')
    else:
        await asyncio_to_thread(play_sound_blocked, segment)


async def main():
    for arg in sys.argv[1:]:
        await play_dial_tone(arg)
        await play_ringing_tone()
        await asyncio.sleep(RINGING_IDLE_SECOND)
        await play_ringing_tone()
        await asyncio.sleep(RINGING_IDLE_SECOND)
    await play_handshake_sound(33600)

    # w = wave.open('output.wav', 'wb')
    # w.setnchannels(NUM_CHANNELS)
    # w.setsampwidth(BYTES_PER_SAMPLE)
    # w.setframerate(SAMPLE_RATE)
    # w.writeframes(buffer)


if __name__ == '__main__':
    asyncio.run(main())


# python sound.py 0696675356 4646415180 2336731416 3608338160 4400826146 6253689638 8482138178 5073643399
# python sound.py 5775577 7557755 7891234
