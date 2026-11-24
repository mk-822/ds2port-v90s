#ifndef DS2PORT_VIEWPORT_H
#define DS2PORT_VIEWPORT_H

#define SCREEN_WIDTH 640
#define SCREEN_HEIGHT 480

typedef struct {
    int x, y, width, height;
} ViewportRect;

static const ViewportRect full_screen = {0, 0, SCREEN_WIDTH, SCREEN_HEIGHT};

static ViewportRect fit_viewport(ViewportRect source)
{
    ViewportRect fitted = full_screen;
    if (source.width * SCREEN_HEIGHT >= source.height * SCREEN_WIDTH)
        fitted.height = source.height * SCREEN_WIDTH / source.width;
    else
        fitted.width = source.width * SCREEN_HEIGHT / source.height;
    fitted.x = (SCREEN_WIDTH - fitted.width) / 2;
    fitted.y = (SCREEN_HEIGHT - fitted.height) / 2;
    return fitted;
}

static int map_coordinate(int value, int origin, int length, int target, int target_length)
{
    if (value <= origin) return target;
    if (value >= origin + length) return target + target_length - 1;
    return target + (value - origin) * target_length / length;
}

static double clamp_coordinate(double value, int origin, int length)
{
    int end = origin + length - 1;
    if (value < origin) return origin;
    return value > end ? end : value;
}

#endif
