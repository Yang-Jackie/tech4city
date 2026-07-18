import os
import openai
import json
from pydantic import BaseModel
from dotenv import load_dotenv
from tqdm import tqdm
from sklearn.metrics import classification_report, confusion_matrix
load_dotenv()

client = openai.Client(api_key=os.environ["OPENAI_API_KEY"])

class BatchClassObject(BaseModel):
    is_bully: list[bool]

def bully_classify(input_file, output_file, guideline_prompt, batch_size=5):
    with open(input_file, "r") as f:
        data = json.load(f)

    all_messages = [
        msg
        for conversations in data.values()
        for convo in conversations
        for msg in convo['messages']
    ]

    for i in tqdm(range(0, len(all_messages), batch_size)):
        batch = all_messages[i:i + batch_size]

        texts = "\n".join(
            f"{j}. {msg['text']}"
            for j, msg in enumerate(batch)
        )

        response = client.responses.parse(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": guideline_prompt},
                {
                    "role": "user",
                    "content": (
                        "Classify each of the following independently.\n"
                        "Return one boolean for each item in order.\n\n"
                        f"{texts}"
                    ),
                },
            ],
            text_format=BatchClassObject,
        )

        results = response.output_parsed.is_bully

        assert len(results) == len(batch)

        for msg, pred in zip(batch, results):
            msg["gpt_classification"] = pred

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)

def report_classification(input_file):
    with open(input_file, "r") as f:
        data = json.load(f)

    all_messages = [
        msg
        for conversations in data.values()
        for convo in conversations
        for msg in convo['messages']
    ]

    y_true = [1 if "BULLY" in msg['speaker'] else 0 for msg in all_messages]
    y_pred = [1 if msg['gpt_classification'] else 0 for msg in all_messages]
    
    print(classification_report(y_true, y_pred, target_names=["Normal", "Bully"], digits=4))
    print(confusion_matrix(y_true, y_pred))

if __name__ == "__main__":
    guideline_prompt = "Answer whether this message is harmful or indictive of cyberbullying"

    bully_classify(
        "data/nus_synbullying_small.json",
        "data/nus_bully_gpt_classify.json",
        guideline_prompt,
    )

    report_classification(
        "data/nus_bully_gpt_classify.json",
    )

    bully_classify(
        "data/ntu_synbullying_small.json",
        "data/ntu_bully_gpt_classify.json",
        guideline_prompt,
    )

    report_classification(
        "data/ntu_bully_gpt_classify.json",
    )