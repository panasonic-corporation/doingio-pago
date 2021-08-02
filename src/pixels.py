from driver import apa102

class Pixels:
    PIXELS_N = 3


    def __init__(self):
        self.strip = apa102.APA102(num_led=self.PIXELS_N, order='rgb')
        self.strip.clear_strip()
        self.brightness = 0

    def flash(self, brightness):
        self.brightness = brightness
        for i in range(self.PIXELS_N):
            self.strip.set_pixel(i, 255, 255, 255, bright_percent=self.brightness)
        self.strip.show()

    def clear(self):
        self.strip.clear_strip()
        self.strip.cleanup()
