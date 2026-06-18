import argparse
import json
import numpy as np
from sklearn.cluster import KMeans
import openai
import os
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

client = openai.Client(api_key=os.environ['OPENAI_API_KEY'])

def kmeans(data, X, output_path, title = None):
    N = len(data)
    n_clusters = int(N**0.25)
    print("n_clusters =", n_clusters)
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto").fit(X)

    samples = {}
    for idx, label in enumerate(kmeans.labels_.tolist()):
        if label not in samples:
            samples[label] = [data[idx]]
        elif len(samples[label]) < 5:
            samples[label].append(data[idx])

    cluster_content = {}
    for idx, item in tqdm(samples.items()):
        response = client.responses.create(
            model="gpt-5.4",
            input=(
                "Return ONLY a valid JSON object. No explanation, no markdown.\n"
                '{"topic": "topic summary of samples"}\n\n'
                f"Samples:\n{chr(10).join(item)}"
            )
        )

        result = json.loads(response.output_text.strip())
        print(result)
        cluster_content[idx] = result["topic"]
    
    with open(output_path+".sample_topic.json", "w") as f:
        json.dump(cluster_content, f, indent=2)

    with open(output_path+".sample.json", "w") as f:
        json.dump(samples, f, indent=2)

    with open(output_path, "w") as f:
        json.dump(kmeans.labels_.tolist(), f)
   
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_file', required=True)
    parser.add_argument('--embeddings', required=True)
    parser.add_argument('--output_file', required=True)
    args = parser.parse_args()

    with open(args.input_file, 'r', encoding="utf-8") as f:
        data = json.load(f) 
    
    embeddings = np.load(args.embeddings)

    kmeans(data, embeddings, args.output_file)
