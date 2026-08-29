import base64
import io

from matplotlib.mathtext import math_to_image

buf = io.BytesIO()
math_to_image(r"$\frac{1}{2}$", buf, format="png", dpi=120, color="white")
b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
print("Success:", b64[:50])
