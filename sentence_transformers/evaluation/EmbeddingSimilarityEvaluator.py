from . import SentenceEvaluator, SimilarityFunction
from torch.utils.data import DataLoader

import torch
import logging
from tqdm import tqdm
from ..util import batch_to_device
import os
import csv
from sklearn.metrics.pairwise import paired_cosine_distances, paired_euclidean_distances, paired_manhattan_distances
from scipy.stats import pearsonr, spearmanr


class EmbeddingSimilarityEvaluator(SentenceEvaluator):
    """
    Evaluate a model based on the similarity of the embeddings by calculating the Spearman and Pearson rank correlation
    in comparison to the gold standard labels.
    The metrics are the cosine similarity as well as euclidean and Manhattan distance
    The returned score is the Spearman correlation with a specified metric.

    The results are written in a CSV. If a CSV already exists, then values are appended.
    """


    def __init__(self, dataloader: DataLoader, main_similarity: SimilarityFunction = None, name:str =''):
        """
        Constructs an evaluator based for the dataset

        The labels need to indicate the similarity between the sentences.

        :param dataloader:
            the data for the evaluation
        :param main_similarity:
            the similarity metric that will be used for the returned score
        """
        self.dataloader = dataloader
        self.main_similarity = main_similarity
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.name = name
        if name:
            name = "_"+name

        self.csv_file: str = "similarity_evaluation"+name+"_results.csv"
        self.csv_headers = ["epoch", "steps", "cosine_pearson", "cosine_spearman", "euclidean_pearson", "euclidean_spearman", "manhattan_pearson", "manhattan_spearman"]

    def __call__(self, model: 'SequentialSentenceEmbedder', output_path: str = None, epoch: int = -1, steps: int = -1) -> float:
        model.eval()
        embeddings1 = []
        embeddings2 = []
        labels = []

        if epoch != -1:
            if steps == -1:
                out_txt = f" after epoch {epoch}:"
            else:
                out_txt = f" in epoch {epoch} after {steps} steps:"
        else:
            out_txt = ":"

        logging.info("Evaluation the model on "+self.name+" dataset"+out_txt)

        self.dataloader.collate_fn = model.smart_batching_collate
        for step, batch in enumerate(tqdm(self.dataloader, desc="Evaluating")):
            features, label_ids = batch_to_device(batch, self.device)
            with torch.no_grad():
                emb1, emb2 = [model(sent_features).to("cpu").numpy() for sent_features in features]

            labels.extend(label_ids.to("cpu").numpy())
            embeddings1.extend(emb1)
            embeddings2.extend(emb2)

        try:
            cosine_scores = 1 - (paired_cosine_distances(embeddings1, embeddings2))
        except Exception as e:
            print(embeddings1)
            print(embeddings2)
            raise(e)

        manhattan_distances = -paired_manhattan_distances(embeddings1, embeddings2)
        euclidean_distances = -paired_euclidean_distances(embeddings1, embeddings2)

        eval_pearson_cosine, _ = pearsonr(labels, cosine_scores)
        eval_spearman_cosine, _ = spearmanr(labels, cosine_scores)

        eval_pearson_manhattan, _ = pearsonr(labels, manhattan_distances)
        eval_spearman_manhattan, _ = spearmanr(labels, manhattan_distances)

        eval_pearson_euclidean, _ = pearsonr(labels, euclidean_distances)
        eval_spearman_euclidean, _ = spearmanr(labels, euclidean_distances)

        logging.info("Cosine-Similarity :\tPearson: {:.4f}\tSpearman: {:4f}".format(
            eval_pearson_cosine, eval_spearman_cosine))
        logging.info("Manhattan-Distance:\tPearson: {:.4f}\tSpearman: {:4f}".format(
            eval_pearson_manhattan, eval_spearman_manhattan))
        logging.info("Euclidean-Distance:\tPearson: {:.4f}\tSpearman: {:4f}".format(
            eval_pearson_euclidean, eval_spearman_euclidean))

        if output_path is not None:
            csv_path = os.path.join(output_path, self.csv_file)
            if not os.path.isfile(csv_path):
                with open(csv_path, mode="w", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(self.csv_headers)
                    writer.writerow([epoch, steps, eval_pearson_cosine, eval_spearman_cosine, eval_pearson_euclidean,
                                     eval_spearman_euclidean, eval_pearson_manhattan, eval_spearman_manhattan])
            else:
                with open(csv_path, mode="a", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([epoch, steps, eval_pearson_cosine, eval_spearman_cosine, eval_pearson_euclidean,
                                     eval_spearman_euclidean, eval_pearson_manhattan, eval_spearman_manhattan])

        if self.main_similarity == SimilarityFunction.COSINE:
            return eval_spearman_cosine
        elif self.main_similarity == SimilarityFunction.EUCLIDEAN:
            return eval_spearman_euclidean
        elif self.main_similarity == SimilarityFunction.MANHATTAN:
            return eval_spearman_manhattan
        elif self.main_similarity is None:
            return max(eval_spearman_cosine, eval_spearman_manhattan, eval_spearman_euclidean)
        else:
            raise ValueError("Unknown main_similarity value")