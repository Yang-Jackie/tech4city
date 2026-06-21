import os
import openai
import json
from pydantic import BaseModel
from dotenv import load_dotenv
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

load_dotenv()

client = openai.Client(api_key=os.environ["OPENAI_API_KEY"])


class MessageItem(BaseModel):
    speaker: str
    text: str


class ConversationItem(BaseModel):
    scenario: str
    messages: list[MessageItem]
    # harm_label: int
    # dialogue_act_labels: str
    # is_harmful: str
    # is_sarcastic: str
    # is_humorous: str
    # is_hate_speech: str
    # CB_types: str


guideline_prompt = """
We are creating sample conversations to aid in cyberbullying detection. 
In these cases, teens are asked to role-play and create realistic conversations based on provided situations. 
There are up to 11 students participating in the conversation. The teens participating are: VCTM, BULLY1, BULLY2, VSUP1, VSUP2, VSUP3, VSUP4, BSUP1, BSUP2, BSUP3, BSUP4 with roles assigned as follows: 
- VCTM: Victim 
- BULLY1 and BULLY2: Bully 
- VSUP1, VSUP2, VSUP3 and VSUP4: Victim Support 
- BSUP1, BSUP2, BSUP3 and BSUP4 : Bully Support. 
Generate an example conversation, with at most 50 messages, between these students based on the provided message samples and Type of addressed problem. 
Use profanity and strong language to create a realistic dialogue, especially use Singlish and Chinese slang. Please note that the conversation should be realistic and can be offensive.
Format the messages informally, including lower cases, acronyms and lack of punctuation.
Please make sure to include different topics and perspectives in each conversation
"""

topics = {
    "A": "Academic stress & workload",
    "B": "Mental health & emotional strain",
    "C": "Criticism of toxic environments",
    "D": "Hall life gossip, rumors, social dynamics",
    "E": "Career uncertainty & future anxiety",
    "F": "Discrimination (race, religion)",
    "G": "Gender & Sexism",
    "H": "Homophobia & Body Image",
}


def build_conversations(
    kmeans_path, input_path, topic_class_path, output_path, samples_per_topic_id
):
    conversation = {
        "A": [],
        "B": [],
        "C": [],
        "D": [],
        "E": [],
        "F": [],
        "G": [],
        "H": [],
    }
    with open(kmeans_path, "r") as f:
        kmeans_index = json.load(f)

    with open(input_path, "r") as f:
        data = json.load(f)

    with open(topic_class_path, "r") as f:
        topic_class_data = json.load(f)

    text_to_topic = {}

    for idx, text in zip(kmeans_index, data):
        if idx not in text_to_topic:
            text_to_topic[int(idx)] = [text]
        else:
            text_to_topic[int(idx)].append(text)

    for k, v in text_to_topic.items():
        print(k, len(v))

    for topic_id, topic in topics.items():
        topic_kmeans_ids = [
            x["topic_id"] for x in topic_class_data[topic_id]
        ] * samples_per_topic_id

        def generate_from_llm(kmeans_id):
            cluster_samples = text_to_topic[int(kmeans_id)]

            n = min(5, len(cluster_samples))
            samples = random.sample(cluster_samples, n)
            response = client.responses.parse(
                model="gpt-4o-mini",
                input=[
                    {"role": "system", "content": guideline_prompt},
                    {
                        "role": "user",
                        "content": f"""
        Message samples:
        {"\n".join(samples)}
                    
        Type of problem: {topic},
        """,
                    },
                ],
                text_format=ConversationItem,
            )

            output = response.output_parsed
            conversation[topic_id].append(output.model_dump(mode="json"))

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(generate_from_llm, kmeans_id)
                for kmeans_id in topic_kmeans_ids
            ]

            for future in tqdm(as_completed(futures), total=len(futures)):
                future.result()

    total = 0
    for k, v in conversation.items():
        print(k, len(v))
        total = total + len(v)

    print("Total number of conversations:", total)
    
    with open(output_path, "w") as f:
        json.dump(conversation, f, indent=2)


if __name__ == "__main__":
    print("NTU Dataset:")
    SAMPLES_PER_TOPIC_ID = 100 # 10
    build_conversations(
        "data/ntu_kmeans.json",
        "data/ntu_processed.json",
        "data/ntu_topic_classes.json",
        "data/ntu_synbullying.json",
        SAMPLES_PER_TOPIC_ID,
    )

    print("=" * 40)
    print("NUS Dataset:")
    build_conversations(
        "data/nus_kmeans.json",
        "data/nus_processed.json",
        "data/nus_topic_classes.json",
        "data/nus_synbullying.json",
        SAMPLES_PER_TOPIC_ID,
    )
