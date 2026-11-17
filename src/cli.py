from .parser.parse_values import (IndexArgs, SearchArgs, SearchDataArgs,
                                  AnswerArgs, AnswerDataArgs, EvaluateArgs)
<<<<<<< Updated upstream
from .models import (DataSource, MinimalSearchResults, MinimalAnswer,
                     AnsweredQuestion)
=======
from .models import DataSource, MinimalSearchResults, MinimalAnswer, AnsweredQuestion
>>>>>>> Stashed changes
from .ingesting import collect_files, load_questions
from .chunking import Chunk
from .helpers import ParseError, Colors, Const, Paths
from .create_data_results import (save_index, save_search_results,
                                  save_answer_dataset)
from .retrieval import (create_indexable_data, retrieve_sources,
                        prepare_retrieval)
from .generation import read_sources, LLM, load_student_search_results
from .evaluate import load_ground_truth, question_recall
from tqdm import tqdm
from pydantic import ValidationError
from pathlib import Path

"""
index –max_chunk_size <int>
search <query> –k <int>
search_dataset –dataset_path <path> –k <int> –save_directory <dir>
answer <query> –k <int>
answer_dataset –student_search_results_path <path> –save_directory <dir>
evaluate –student_search_results_path <path> –dataset_path <path>
"""


""" from models import (MinimalSource, UnansweredQuestion,
                    AnsweredQuestion, RagDataset,
                    MinimalSearchResults, MinimalAnswer,
                    StudentSearchResults,
                    StudentSearchResultsAndAnswer) """

""" Each should create a manager with the customized values """


class Cli:
    def index(self, max_chunk_size: int = 2000) -> None:
        try:
            args = IndexArgs(max_chunk_size=max_chunk_size)
        except ValidationError as e:
            msgs = [f"'{err['loc'][0]}' - {err['msg']}" for err in e.errors()]
            raise ParseError("\n".join(msgs)) from None

        all_paths = collect_files()
        chunk = Chunk(args.max_chunk_size)
        chunks: list[DataSource] = []

        for path in tqdm(all_paths, desc="Ingestion", leave=False):
            suffix = path.suffix.lower()

            if suffix == ".py":
                chunks.extend(chunk.chunk_python(path))

            elif suffix == ".md":
                chunks.extend(chunk.chunk_markdown(path))

            elif suffix == ".txt":
                chunks.extend(chunk.chunk_text(path))

        save_index(chunks=chunks)
        create_indexable_data(chunks=chunks)

    def search(self, query: str, k: int = 3) -> None:
        try:
            args = SearchArgs(k=k, query=query)
        except ValidationError as e:
            msgs = [f"'{err['loc'][0]}' - {err['msg']}" for err in e.errors()]
            raise ParseError("\n".join(msgs)) from None

        retriever, chunk_list = prepare_retrieval(args.k)

        sources, warning = retrieve_sources(args.query, args.k, retriever,
                                            chunk_list)
        if warning == Const.WORD_ERROR:
            print(f"{Colors.BOLD}{Colors.YELLOW}Warning:{Colors.END} "
                  "The question has no searchable words")
        elif warning == Const.CHUNK_ERROR:
            print(f"{Colors.BOLD}{Colors.YELLOW}Warning:{Colors.END} No "
                  "chunk matches this question")

        for i, source in enumerate(sources, start=1):
            print(f"{Colors.BOLD}{Colors.BLUE}Result {i}:{Colors.END} "
                  f"{source}")

    def search_dataset(self, dataset_path: str = Paths.DATASET_PATH_CODE,
                       save_directory: str = Paths.SAVE_DIRECTORY_SEARCH,
                       k: int = 3) -> None:
        try:
            args = SearchDataArgs(dataset_path=dataset_path,
                                  save_directory=save_directory,
                                  k=k)

        except ValidationError as e:
            msgs = [f"'{err['loc'][0]}' - {err['msg']}" for err in e.errors()]
            raise ParseError("\n".join(msgs)) from None

        word = 0
        chunk = 0

        retriever, chunk_list = prepare_retrieval(args.k)

        questions = load_questions(args.dataset_path)
        search_results: list[MinimalSearchResults] = []

        for question in tqdm(questions["rag_questions"],
                             desc="Searching Datasets",
                             leave=False):
            sources, warnings = retrieve_sources(question["question"],
                                                 args.k,
                                                 retriever,
                                                 chunk_list)
            if warnings == Const.WORD_ERROR:
                word += 1
            elif warnings == Const.CHUNK_ERROR:
                chunk += 1

            model = MinimalSearchResults(question_id=question
                                         ["question_id"],
                                         question=question["question"],
                                         retrieved_sources=sources)
            search_results.append(model)

        if word != 0:
            if word == 1:
                print(f"{Colors.BOLD}{Colors.YELLOW}Warning:{Colors.END} "
                      f"{word} question has no searchable words")
            else:
                print(f"{Colors.BOLD}{Colors.YELLOW}Warning:{Colors.END} "
                      f"{word} questions have no searchable words")
        if chunk != 0:
            if chunk == 1:
                print(f"{Colors.BOLD}{Colors.YELLOW}Warning:{Colors.END} "
                      f"{chunk} question has no matching chunks")
            else:
                print(f"{Colors.BOLD}{Colors.YELLOW}Warning:{Colors.END} "
                      f"{chunk} questions have no matching chunks")

        filename = Path(args.dataset_path).name

        save_search_results(search_results=search_results,
                            output_path=args.save_directory,
                            k=args.k,
                            filename=filename)

    def answer(self, query: str, k: int = 3) -> None:
        try:
            args = AnswerArgs(query=query, k=k)
        except ValidationError as e:
            msgs = [f"'{err['loc'][0]}' - {err['msg']}" for err in e.errors()]
            raise ParseError("\n".join(msgs)) from None

        retriever, chunk_list = prepare_retrieval(args.k)

        source, warning = retrieve_sources(args.query, args.k, retriever,
                                           chunk_list)
        if warning == Const.WORD_ERROR:
            print(f"{Colors.BOLD}{Colors.YELLOW}Warning:{Colors.END} "
                  "The question has no searchable words")
            return
        elif warning == Const.CHUNK_ERROR:
            print(f"{Colors.BOLD}{Colors.YELLOW}Warning:{Colors.END} No "
                  "chunk matches this question")
            return
        texts = read_sources(sources=source)

        print(f"\n{Colors.BOLD}{Colors.BLUE}Initializing the LLM..."
              f"{Colors.END}")
        model = LLM()
        print(f"\n{Colors.BOLD}{Colors.BLUE}Processing the prompt..."
              f"{Colors.END}")
        response = model.generate_response(args.query, source, texts)
        print(f"\n{Colors.BOLD}{Colors.GREEN}Response: {Colors.END}{response}")

    def answer_dataset(
        self,
        student_search_results_path: str = Paths.SAVE_DIRECTORY_SEARCH_CODE,
        save_directory: str = Paths.SAVE_DIRECTORY_ANSWER
    ) -> None:

        try:
            args = AnswerDataArgs(
                student_search_results_path=student_search_results_path,
                save_directory=save_directory)
        except ValidationError as e:
            msgs = [f"'{err['loc'][0]}' - {err['msg']}" for err in e.errors()]
            raise ParseError("\n".join(msgs)) from None

        results = load_student_search_results(
            args.student_search_results_path)

        print(f"\n{Colors.BOLD}{Colors.BLUE}Initializing the LLM..."
              f"{Colors.END}")
        model = LLM()
        answers = []

        for result in tqdm(results.search_results,
                           desc="Processing Questions",
                           leave=False):
            texts = read_sources(sources=result.retrieved_sources)
            temp_answer = model.generate_response(
                result.question,
                result.retrieved_sources,
                texts)
            answer = MinimalAnswer(
                question_id=result.question_id,
                question=result.question,
                retrieved_sources=result.retrieved_sources,
                answer=temp_answer)
            answers.append(answer)

        filename = Path(args.student_search_results_path).name

        save_answer_dataset(answers, args.save_directory,
                            results.k, filename)

<<<<<<< Updated upstream
    def evaluate(
        self,
        student_search_results_path: str = Paths.SAVE_DIRECTORY_SEARCH_CODE,
        dataset_path: str = Paths.ANSWERED_QUESTIONS_CODE
    ) -> None:

=======
    def evaluate(self,
                 student_search_results_path: str,
                 dataset_path: str) -> None:
>>>>>>> Stashed changes
        try:
            args = EvaluateArgs(
                student_search_results_path=student_search_results_path,
                dataset_path=dataset_path)
<<<<<<< Updated upstream
=======
            results = load_student_search_results(
                args.student_search_results_path)
            ground_truth = load_ground_truth(args.dataset_path)

            retrieved = {r.question_id: r.retrieved_sources
                         for r in results.search_results}
            known_ids = {q.question_id for q in ground_truth.rag_questions}
            unknown = {qid for qid in retrieved if qid not in known_ids}
            if unknown:
                print(f"{Colors.BOLD}{Colors.YELLOW}Warning:{Colors.END} "
                      f"{len(unknown)} question_id(s) are not in the dataset")

            missing = len(known_ids - retrieved.keys())
            print(f"{Colors.BOLD}{Colors.YELLOW}Warning:{Colors.END} "
                  f"{missing} question(s) have no search results")

            total = 0.0
            for q in ground_truth.rag_questions:
                truth = q.sources if isinstance(q, AnsweredQuestion) else []
                total += question_recall(truth,
                                         retrieved.get(q.question_id, []),
                                         results.k)
            questions = len(ground_truth.rag_questions)
            recall = total / questions if questions else 0.0

            print(f"{Colors.BOLD}{Colors.BLUE}Recall@{results.k}:"
                  f"{Colors.END} {recall:.3f}")
>>>>>>> Stashed changes
        except ValidationError as e:
            msgs = [f"'{err['loc'][0]}' - {err['msg']}" for err in e.errors()]
            raise ParseError("\n".join(msgs)) from None

        results = load_student_search_results(
            args.student_search_results_path)
        ground_truth = load_ground_truth(args.dataset_path)

        retrieved = {r.question_id: r.retrieved_sources
                     for r in results.search_results}
        known_ids = {q.question_id for q in ground_truth.rag_questions}
        unknown = {qid for qid in retrieved if qid not in known_ids}
        if unknown:
            print(f"{Colors.BOLD}{Colors.YELLOW}Warning:{Colors.END} "
                  f"{len(unknown)} question_id(s) are not in the dataset")
        missing = len(known_ids - retrieved.keys())
        if missing:
            print(f"{Colors.BOLD}{Colors.YELLOW}Warning:{Colors.END} "
                  f"{missing} question(s) have no search results")

        total = 0.0
        for q in ground_truth.rag_questions:
            truth = q.sources if isinstance(q, AnsweredQuestion) else []
            total += question_recall(truth,
                                     retrieved.get(q.question_id, []),
                                     results.k)

        questions = len(ground_truth.rag_questions)
        recall = total / questions if questions else 0.0
        print(f"{Colors.BOLD}{Colors.BLUE}Recall@{results.k}:{Colors.END} "
              f"{recall:.3f}")


"""
#TODO
README


- evaluate, README

- Reorganize folders, test
"""
