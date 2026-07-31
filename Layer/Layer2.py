import numpy as np
import torch
import torch.nn as nn
from sentence_transformers import SentenceTransformer

TEXT_EMBEDDING_DIMENSION = 768
USER_EMBEDDING_DIMENSION = 128


class Layer2:
    def __init__(
        self,
        classifier_head_model_path,
        node2vec_embedding_path=None,
        text_embedding_model="google/embeddinggemma-300m",
    ):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.classifier_head = nn.Sequential(
            nn.Linear(TEXT_EMBEDDING_DIMENSION + USER_EMBEDDING_DIMENSION, 128),
            nn.Dropout(),
            nn.ReLU(),
            nn.Linear(128, 1),
        )
        self.classifier_head_model_path = classifier_head_model_path
        self.classifier_head.load_state_dict(
            torch.load(
                classifier_head_model_path,
                map_location=self.device,
                weights_only=True,
            )
        )
        self.classifier_head.eval()
        self.classifier_head.to(self.device)

        self.embedding_gemma = SentenceTransformer(text_embedding_model)
        self.embedding_gemma.eval()
        self.embedding_gemma.to(self.device)

        self.node2vec_wv = None
        if node2vec_embedding_path is not None:
            from gensim.models import KeyedVectors

            self.node2vec_wv = KeyedVectors.load_word2vec_format(
                node2vec_embedding_path
            )

    def predict(self, message: str, user_id: int | None = None):
        text_emb = np.asarray(self.embedding_gemma.encode_query(message)).reshape(-1)
        if text_emb.size != TEXT_EMBEDDING_DIMENSION:
            raise ValueError(
                "Layer 2 text embedding must contain "
                f"{TEXT_EMBEDDING_DIMENSION} values, received {text_emb.size}."
            )

        if user_id is None:
            user_emb = np.zeros(USER_EMBEDDING_DIMENSION, dtype=text_emb.dtype)
            user_embedding_strategy = "zero"
        else:
            if self.node2vec_wv is None:
                raise ValueError(
                    "A Node2Vec artifact is required when Layer 2 receives a user ID."
                )
            user_emb = np.asarray(self.node2vec_wv.get_vector(user_id)).reshape(-1)
            user_embedding_strategy = "node2vec"
        if user_emb.size != USER_EMBEDDING_DIMENSION:
            raise ValueError(
                "Layer 2 user embedding must contain "
                f"{USER_EMBEDDING_DIMENSION} values, received {user_emb.size}."
            )

        combined_emb = np.concatenate((text_emb, user_emb), axis=0)
        combined_emb_tensor = torch.from_numpy(
            combined_emb.astype(np.float32, copy=False)
        ).to(self.device)

        with torch.no_grad():
            out = self.classifier_head(combined_emb_tensor)
            out = torch.sigmoid(out)
            pred = out.detach().cpu().numpy()[0]

        return {
            "layer": 2,
            "status": "bully" if pred >= 0.5 else "normal",
            "raw_label": "bully" if pred >= 0.5 else "normal",
            "normal_score": round(float(1 - pred), 4),
            "bully_score": round(float(pred), 4),
            "model_dir": str(self.classifier_head_model_path),
            "user_embedding_strategy": user_embedding_strategy,
        }


if __name__ == "__main__":
    layer2 = Layer2(
        "data/ntu_layer2_classifier_head.pth", "data/ntu_node2vec_embeddings.emb"
    )
    print(
        layer2.predict(
            "whatever lah. saw him crying last week when everyone was "
            "at the event. super embarrassing.",
            810,
        )
    )
