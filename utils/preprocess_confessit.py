import json
from dotenv import load_dotenv
import argparse
import re
load_dotenv()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_file', required=True)
    parser.add_argument('--output_file', required=True)

    args = parser.parse_args()
    
    with open(args.input_file, 'r', encoding="utf-8") as f:
        data = json.load(f)

    output = []
    for m in data['messages']:
            text = ' '.join(t.strip() if isinstance(t, str) else "" for t in m['text']).strip()
            if text[:3] == "---": 
                text = text[3:]
            text = re.sub(r'---.*$', '', text, flags=re.DOTALL)
            text = text.encode("ascii", "ignore").decode("ascii")
            text = text.strip()
            if len(text) > 20:
                output.append(text)

    with open(args.output_file, 'w', encoding="utf-8") as f:
        json.dump(output, f, indent=2)
        f.close()