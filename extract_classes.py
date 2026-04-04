import re
import sys

def analyze():
    with open("business_dump.html", "r", encoding="utf-8") as f:
        html = f.read()

    with open("classes.txt", "w", encoding="utf-8") as out:
        out.write("--- Searching for Yorumlar ---\n")
        # find where "Yorumlar" is and print 100 characters before it
        idxs = [m.start() for m in re.finditer(r"Yorumlar", html)]
        for i in idxs[:5]:
            out.write(html[max(0, i-250):i+50] + "\n\n")

        out.write("\n--- Searching for yıldız ---\n")
        idxs = [m.start() for m in re.finditer(r"yıldız", html)]
        for i in idxs[:5]:
            out.write(html[max(0, i-250):i+50] + "\n\n")

if __name__ == "__main__":
    analyze()
