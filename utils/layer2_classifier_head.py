import json
from tqdm import tqdm
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, random_split
import numpy as np
from sklearn.metrics import classification_report
import matplotlib.pyplot as plt
from sentence_transformers import SentenceTransformer
from node2vec import Node2Vec
import networkx as nx

model = nn.Sequential(
    nn.Linear(768 + 128, 128), nn.Dropout(), nn.ReLU(), nn.Linear(128, 1)
)
criterion = nn.BCEWithLogitsLoss()
optimizer = torch.optim.Adam(model.parameters())
device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)
embeddinggemma = SentenceTransformer("google/embeddinggemma-300m")

EPOCHS = 200
EARLY_STOP = 5


def layer_2(input_file, output_file, batch_size=32):
    with open(input_file, "r") as f:
        data = json.load(f)

    all_msg = [
        msg
        for conversations in data.values()
        for convo in conversations
        for msg in convo["messages"]
    ]

    all_convos = [convo for conversations in data.values() for convo in conversations]

    G = nx.Graph()

    for idx, convo in enumerate(all_convos):
        user_ids = set((text["user_id"], text["speaker"]) for text in convo["messages"])
        convo_id = "C" + str(idx)
        for id, role in user_ids:
            G.add_edge(id, convo_id, role=role)

    node2vec = Node2Vec(G)
    node2vec_model = node2vec.fit()

    embeddings = []

    for i in tqdm(range(0, len(all_msg), batch_size)):
        batch = all_msg[i : i + batch_size]

        texts = [msg["text"] for msg in batch]
        node2vec_emb = [
            node2vec_model.wv.get_vector(int(msg["user_id"])) for msg in batch
        ]
        node2vec_emb = np.array(node2vec_emb)
        document_embeddings = embeddinggemma.encode_document(texts)
        document_embeddings = np.concat((document_embeddings, node2vec_emb), axis=-1)
        embeddings.append(document_embeddings)

    embeddings_np = np.concat(embeddings)

    X = torch.from_numpy(embeddings_np).to(device)
    y = torch.Tensor([1 if "BULLY" in msg["speaker"] else 0 for msg in all_msg]).to(
        device
    )

    dataset = TensorDataset(X, y)
    train_dataset, val_dataset = random_split(dataset, [0.8, 0.2])
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    train_losses, val_losses = [], []
    best_train_loss, best_val_loss = float("inf"), float("inf")
    counter = 0
    for epoch in range(EPOCHS):
        model.train()
        train_loss = 0.0
        for X_train, y_train in train_loader:
            out = model(X_train)
            loss = criterion(out.squeeze(), y_train)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * X_train.size(0)

        train_loss /= len(train_loader.dataset)

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for X_val, y_val in val_loader:
                out = model(X_val)
                loss = criterion(out.squeeze(), y_val)

                val_loss += loss.item() * X_val.size(0)

        val_loss /= len(val_loader.dataset)

        print(
            f"Epoch {epoch + 1}: Train loss = {train_loss:.4f}, Val loss = {val_loss:.4f}, Best Val Loss = {best_val_loss:.4f}"
        )
        train_losses.append(train_loss)
        val_losses.append(val_loss)

        if val_loss >= best_val_loss:
            counter = counter + 1
        else:
            best_val_loss = val_loss
            counter = 0

        if counter == EARLY_STOP:
            break

    torch.save(model.state_dict(), output_file)

    plt.plot(train_losses, "r")
    plt.plot(val_losses, "b")
    plt.legend(["train", "val"])
    plt.savefig("train_val_loss_layer2.png")

    model.eval()
    y_pred = []
    y_true = []
    with torch.no_grad():
        for X_val, y_val in val_loader:
            out = model(X_val)
            out = nn.functional.sigmoid(out)
            pred = out.round().detach().cpu().numpy()
            labels = y_val.detach().cpu().numpy()

            y_pred.append(pred)
            y_true.append(labels)

    y_pred = np.concat(y_pred)
    y_true = np.concat(y_true)

    print(
        classification_report(
            y_true, y_pred, target_names=["Normal", "Bully"], digits=4
        )
    )


if __name__ == "__main__":
    layer_2("ntu_synbullying_with_id.json", "ntu_layer2_classifier_head.pth", 128)
