
from PIL import Image
import numpy as np
# np.set_printoptions(threshold=sys.maxsize)


def dump_1bit(pixels: np.ndarray):
    flat_pixels = (pixels.flatten() > 127).astype(np.uint8)  # Convert to binary (0 or 1)
    result_array = np.packbits(flat_pixels)  # Use np.packbits to pack bits into bytes
    return result_array

# Load image and convert to grayscale
image = Image.open("/Users/chengmingzhang/CodingProjects/Software/Distiller-SAM-Firmware/Asset/Loading-A-2-1-inch.png").convert("L")
converted_pixels = dump_1bit(np.array(image.transpose(
            Image.FLIP_TOP_BOTTOM), dtype=np.uint8))


# Save to binary file
file_path = '/Users/chengmingzhang/CodingProjects/Software/Distiller-SAM-Firmware/src/V0.2.2/bin/loading1.bin'
with open(file_path, 'wb') as f:
    f.write(converted_pixels.tobytes())  # Write packed bits

print("Data written to file:", file_path)