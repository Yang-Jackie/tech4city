from sentence_transformers import SentenceTransformer
import json
import numpy as np
from tqdm import tqdm
import torch

model = SentenceTransformer("google/embeddinggemma-300m")
model.eval()

batch_size = 32

def process(input_path, output_path):
  with open(input_path, 'r') as f:
      documents = json.load(f)

  document_embeddings = []

  with torch.no_grad():
    for idx in tqdm(range(0, len(documents), batch_size)):
      doc_emb = model.encode(documents[idx:idx+batch_size], convert_to_numpy=True)
      document_embeddings.extend(doc_emb)

  document_embeddings = np.stack(document_embeddings)
  print(document_embeddings.shape)

  np.save(output_path, document_embeddings)

if __name__ == "__main__":
    process('data/nus_processed.json', 'data/nus_processed.npy')
    process('data/ntu_processed.json', 'data/ntu_processed.npy')