from .parser.parse_values import (IndexArgs, SearchArgs, SearchDataArgs,
                                  AnswerArgs, AnswerDataArgs)
from .models import DataSource, MinimalSearchResults, MinimalAnswer
from .ingesting import collect_files, load_questions
from .chunking import Chunk
from .helpers import ParseError, Colors, WORD_ERROR, CHUNK_ERROR
from .create_data_results import (save_index, save_search_results,
                                  save_answer_dataset)
from .retrieval import (create_indexable_data, retrieve_sources,
                        prepare_retrieval)
from .generation import read_sources, LLM, load_student_search_results
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

    def search(self, query: str, k: int = 5) -> None:
        try:
            args = SearchArgs(k=k, query=query)
        except ValidationError as e:
            msgs = [f"'{err['loc'][0]}' - {err['msg']}" for err in e.errors()]
            raise ParseError("\n".join(msgs)) from None

        retriever, chunk_list = prepare_retrieval(args.k)

        sources, warning = retrieve_sources(args.query, args.k, retriever,
                                            chunk_list)
        if warning == WORD_ERROR:
            print(f"{Colors.BOLD}{Colors.YELLOW}Warning:{Colors.END} "
                  "The question has no searchable words")
        elif warning == CHUNK_ERROR:
            print(f"{Colors.BOLD}{Colors.YELLOW}Warning:{Colors.END} No "
                  "chunk matches this question")

        for i, source in enumerate(sources, start=1):
            print(f"{Colors.BOLD}{Colors.BLUE}Result {i}:{Colors.END} "
                  f"{source}")

    def search_dataset(self, dataset_path: str, save_directory: str,
                       k: int = 5) -> None:
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
            if warnings == WORD_ERROR:
                word += 1
            elif warnings == CHUNK_ERROR:
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

    def answer(self, query: str, k: int = 5) -> None:
        try:
            args = AnswerArgs(query=query, k=k)
        except ValidationError as e:
            msgs = [f"'{err['loc'][0]}' - {err['msg']}" for err in e.errors()]
            raise ParseError("\n".join(msgs)) from None

        retriever, chunk_list = prepare_retrieval(args.k)

        source, warning = retrieve_sources(args.query, args.k, retriever,
                                           chunk_list)
        if warning == WORD_ERROR:
            print(f"{Colors.BOLD}{Colors.YELLOW}Warning:{Colors.END} "
                  "The question has no searchable words")
            return
        elif warning == CHUNK_ERROR:
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

    def answer_dataset(self, student_search_results_path: str,
                       save_directory: str) -> None:
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

    def evaluate(self, student_search_results_path: str,
                 dataset_path: str) -> None:
        ...


"""
#TODO
Starting on Answer dataset
- Validate arguments - done
- Load json files from search_dataset - done
- Load input file into the model - turn it into a StudentSearchResults
    - check if there are malformed files
    - each entry is already a MinimalSearchResults
    - Remember k
- Load the LLM once - done
- Loop over search results with tqdm
    - read_sources(entry.retrieved_sources) - texts
    - ll.generate_response(entry.question, entry.retrieved_sources, texts) -
    answer string
    - build a minimal answer, append it to a list
- Put the list and k into a StudentSearchResultsAndAnser and write it to
save_directory, using the same file name as the input file


- evaluate, README

- Reorganize folders, test
"""
