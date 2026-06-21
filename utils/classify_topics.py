import os
import openai
import json
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

client = openai.Client(api_key=os.environ["OPENAI_API_KEY"])


class ClassObject(BaseModel):
    topic_class: str


def classify_topics(input_file, output_file, guideline_prompt):
    topics = {
        "A": [],
        "B": [],
        "C": [],
        "D": [],
        "E": [],
        "F": [],
        "G": [],
        "H": [],
    }

    with open(input_file, "r") as f:
        data = json.load(f)

    for idx, text in data.items():
        response = client.responses.parse(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": guideline_prompt},
                {"role": "user", "content": text},
            ],
            text_format=ClassObject,
        )

        output = response.output_parsed
        topics[output.topic_class[0]].append({
            "topic_id": int(idx),
            "topic_text": text
        })

    with open(output_file, "w") as f:
        json.dump(topics, f, indent=2)


if __name__ == "__main__":
    guideline_prompt = """
Classify this conversation topic summary by one of 4 cases, answer by A, B, C, D, E, F, G, or H:
- A. Academic stress & workload
- B. Mental health & emotional strain
- C. Criticism of toxic environments
- D. Hall life gossip, rumors, social dynamics
- E. Career uncertainty & future anxiety
- F. Discrimination (race, religion)
- G. Gender & Sexism
- H. Homophobia & Body Image
"""

    classify_topics(
        "data/nus_kmeans.json.sample_topic.json",
        "data/nus_topic_classes.json",
        guideline_prompt,
    )
    classify_topics(
        "data/ntu_kmeans.json.sample_topic.json",
        "data/ntu_topic_classes.json",
        guideline_prompt,
    )
