import torch
import torch.nn as nn
import numpy as np
from sentence_transformers import SentenceTransformer
from gensim.models import KeyedVectors


class Layer2:
    def __init__(
        self,
        classifier_head_model_path,
        node2vec_embedding_path,
        text_embedding_model="google/embeddinggemma-300m",
    ):
        self.classifier_head = nn.Sequential(
            nn.Linear(768 + 128, 128), nn.Dropout(), nn.ReLU(), nn.Linear(128, 1)
        )
        self.classifier_head_model_path = classifier_head_model_path
        self.classifier_head.load_state_dict(
            torch.load(classifier_head_model_path, weights_only=True)
        )
        self.classifier_head.eval()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.classifier_head.to(self.device)

        self.embedding_gemma = SentenceTransformer(text_embedding_model)
        self.embedding_gemma.eval()
        self.embedding_gemma.to(self.device)

        self.node2vec_wv = KeyedVectors.load_word2vec_format(node2vec_embedding_path)

    def predict(self, message: str, user_id: int):

        text_emb = self.embedding_gemma.encode_query(message)
        user_emb = self.node2vec_wv.get_vector(user_id)

        combined_emb = np.concat((text_emb, user_emb), axis=0)
        combined_emb_tensor = torch.from_numpy(combined_emb).to(self.device)

        with torch.no_grad():
            out = self.classifier_head(combined_emb_tensor)
            out = nn.functional.sigmoid(out)
            pred = out.detach().cpu().numpy()[0]

        return {
            "layer": 2,
            "status": "bully" if pred >= 0.5 else "normal",
            "raw_label": "bully" if pred >= 0.5 else "normal",
            "normal_score": round(float(1 - pred), 4),
            "bully_score": round(float(pred), 4),
            "model_dir": self.classifier_head_model_path,
        }


if __name__ == "__main__":
    layer2 = Layer2(
        "data/ntu_layer2_classifier_head.pth", "data/ntu_node2vec_embeddings.emb"
    )
    print(
        layer2.predict(
            "whatever lah. saw him crying last week when everyone was at the event. super embarrassing.",
            810,
        )
    )
