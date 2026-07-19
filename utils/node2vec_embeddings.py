import networkx as nx
from node2vec import Node2Vec
import json


def node2vec_embeddings(input_file, output_file):
    with open(input_file, "r") as f:
        data = json.load(f)

    all_convos = [convo for conversations in data.values() for convo in conversations]

    G = nx.Graph()

    for idx, convo in enumerate(all_convos):
        user_ids = set((text["user_id"], text["speaker"]) for text in convo["messages"])
        convo_id = "C" + str(idx)
        for id, role in user_ids:
            G.add_edge(id, convo_id, role=role)

    node2vec = Node2Vec(G)
    node2vec_model = node2vec.fit()

    node2vec_model.wv.save_word2vec_format(output_file)


if __name__ == "__main__":
    node2vec_embeddings(
        "data/ntu_synbullying_with_id.json", "data/ntu_node2vec_embeddings.emb"
    )

    # node2vec_embeddings(
    #    "data/nus_synbullying_with_id.json",
    #    "data/nus_node2vec_embeddings.emb"
    # )
