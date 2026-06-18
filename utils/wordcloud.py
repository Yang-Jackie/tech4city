from wordcloud import WordCloud, STOPWORDS
import matplotlib.pyplot as plt
import argparse
import json

stopwords = set(STOPWORDS)

def show_wordcloud(data, output_path, title = None):
    wordcloud = WordCloud(
        background_color='white',
        stopwords=stopwords,
        max_words=200,
        max_font_size=40, 
        scale=3,
        random_state=1 # chosen at random by flipping a coin; it was heads
    ).generate(str(data))

    fig = plt.figure(1, figsize=(12, 12))
    plt.axis('off')
    if title: 
        fig.suptitle(title, fontsize=20)
        fig.subplots_adjust(top=2.3)

    plt.imsave(output_path, wordcloud)
    # plt.imshow(wordcloud)
    # plt.show()
   
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_file', required=True)
    parser.add_argument('--output_file', required=True)
    args = parser.parse_args()

    with open(args.input_file, 'r', encoding="utf-8") as f:
        data = json.load(f) 

    show_wordcloud(data, args.output_file)
