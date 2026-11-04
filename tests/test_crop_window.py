from birdframe.art import crop_window


def test_window_has_aspect_and_contains_bird():
    l, t, r, b = crop_window((1000, 800), (0.4, 0.4, 0.5, 0.5), aspect=0.72)
    assert abs((r - l) / (b - t) - 0.72) < 0.01
    assert l <= 400 and r >= 500 and t <= 320 and b >= 400


def test_clip_keeps_window_inside_region():
    clip = (0.5, 0.1, 0.95, 0.9)  # right page of a spread
    l, t, r, b = crop_window((1000, 800), (0.52, 0.3, 0.8, 0.55), aspect=0.72, clip=clip)
    assert l >= 500 and r <= 950 and t >= 80 and b <= 720
    assert abs((r - l) / (b - t) - 0.72) < 0.01


def test_no_box_with_clip_uses_clip_region():
    l, t, r, b = crop_window((1000, 1000), None, aspect=0.5, clip=(0.2, 0.0, 0.8, 1.0))
    assert l >= 200 and r <= 800
