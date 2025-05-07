import chess
import chess.pgn
import chess.engine
import io
import sys # Import sys module

# IMPORTANT: User needs to configure these paths
# Example for Linux/macOS if Maia is in the same directory:
# MAIA_EXECUTABLE_PATH = "./maia"
# Example for Windows:
# MAIA_EXECUTABLE_PATH = "maia.exe"
# Ensure this path points to your MAIA ENGINE executable, not a generic Lc0.
LC0_EXECUTABLE_PATH = "/opt/homebrew/bin/lc0"  # <--- UPDATE THIS PATH
# Example weights file (choose one, e.g., maia-1100.pb.gz, maia-1500.pb.gz)
MAIA_WEIGHTS_PATH = "maia-1100.pb"  # <--- UPDATE THIS PATH

def get_maia_top_move(engine, fen_str):
    """
    Uses an active Maia engine instance to get its top predicted move for the given FEN.
    Returns a chess.Move object or None on error.
    """
    try:
        board = chess.Board(fen_str)
        # Ask Maia for its top move.
        # Maia is trained for next-move prediction.
        # As per Maia documentation, use a node limit of 1.
        info = engine.analyse(board, chess.engine.Limit(nodes=1))

        if info and "pv" in info and info["pv"]:
            return info["pv"][0]  # The first move in the principal variation
        else:
            print("Error: Maia did not return a principal variation (top move).")
            return None
    # Removed EngineTerminatedError and FileNotFoundError from here as engine is managed outside
    except Exception as e:
        print(f"Error during Maia analysis for FEN {fen_str}: {e}")
        return None

def process_pgn_file(input_pgn_filepath, easy_output_filepath, hard_output_filepath):
    """
    Reads puzzles from an input PGN file, classifies them, and writes them
    to separate PGN files based on difficulty, in batches.
    """
    easy_puzzles_pgn_strings = [] # Still used for summary count
    hard_puzzles_pgn_strings = [] # Still used for summary count
    error_puzzles_count = 0
    processed_puzzles_count = 0
    engine = None

    PUZZLES_PER_BATCH = 25
    easy_batch_num = 0
    hard_batch_num = 0
    easy_puzzles_in_current_batch = 0
    hard_puzzles_in_current_batch = 0
    f_easy = None
    f_hard = None

    # Derive base names for output batch files
    easy_base_name = easy_output_filepath.rsplit('.', 1)[0]
    hard_base_name = hard_output_filepath.rsplit('.', 1)[0]

    print(f"Starting puzzle difficulty classification for file: {input_pgn_filepath}")
    print(f"Puzzles will be written in batches of {PUZZLES_PER_BATCH}.")
    print(f"Easy puzzle batches will use base name: {easy_base_name}_batch_N.pgn")
    print(f"Hard puzzle batches will use base name: {hard_base_name}_batch_N.pgn")

    try:
        # Initialize Maia engine once
        try:
            engine = chess.engine.SimpleEngine.popen_uci(LC0_EXECUTABLE_PATH)
            engine.configure({"WeightsFile": MAIA_WEIGHTS_PATH})
            print("Maia engine initialized successfully.")
        except chess.engine.EngineTerminatedError:
            print(f"Error: Maia engine terminated unexpectedly during initialization. Check executable path: '{LC0_EXECUTABLE_PATH}' and that it's runnable.")
            return
        except FileNotFoundError:
            print(f"Error: Maia executable not found at '{LC0_EXECUTABLE_PATH}' or weights not found at '{MAIA_WEIGHTS_PATH}'. Please check paths.")
            return
        except Exception as e:
            print(f"Error initializing Maia engine: {e}")
            print("This might be due to incorrect paths, Maia engine issues, or missing/corrupt weights file.")
            return

        with open(input_pgn_filepath, 'r', encoding='utf-8') as pgn_file: # Add encoding='utf-8'
            while True:
                game = chess.pgn.read_game(pgn_file)
                if game is None:
                    break  # End of file

                processed_puzzles_count += 1
                current_puzzle_id_str = f"puzzle #{processed_puzzles_count} (Event: {game.headers.get('Event', 'N/A')})"
                print(f"\nProcessing {current_puzzle_id_str}...")

                exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
                current_pgn_string = game.accept(exporter)

                fen = game.headers.get("FEN")
                setup = game.headers.get("SetUp")

                if setup == "1" and not fen:
                    print(f"Error: {current_puzzle_id_str} has SetUp='1' but no FEN tag. Skipping.")
                    error_puzzles_count += 1
                    continue
                if not fen:
                    print(f"Error: {current_puzzle_id_str} FEN tag not found. Cannot determine position. Skipping.")
                    error_puzzles_count += 1
                    continue

                mainline_moves = list(game.mainline_moves())
                if not mainline_moves:
                    print(f"Error: {current_puzzle_id_str} no solution move found. Skipping.")
                    print(f"  Headers: {game.headers}")
                    if game.errors:
                        print(f"  Parser errors: {game.errors}")
                    error_puzzles_count += 1
                    continue
                
                solution_move_object = mainline_moves[0]
                
                maia_top_move = get_maia_top_move(engine, fen) # Pass engine instance

                if not maia_top_move:
                    print(f"  Could not get Maia's top move for {current_puzzle_id_str}. Skipping classification.")
                    error_puzzles_count += 1
                    continue

                if solution_move_object == maia_top_move:
                    print(f"  Classification for {current_puzzle_id_str}: Easy")
                    easy_puzzles_pgn_strings.append(current_pgn_string)
                    if f_easy is None or easy_puzzles_in_current_batch >= PUZZLES_PER_BATCH:
                        if f_easy:
                            f_easy.close()
                            print(f"Closed easy batch file: {f_easy.name}")
                        easy_batch_num += 1
                        current_easy_filename = f"{easy_base_name}_batch_{easy_batch_num}.pgn"
                        try:
                            f_easy = open(current_easy_filename, 'w', encoding='utf-8')
                            print(f"Opened new easy batch file: {current_easy_filename}")
                        except IOError as e:
                            print(f"Error opening easy batch file {current_easy_filename}: {e}")
                            f_easy = None # Prevent further writes if open failed
                        easy_puzzles_in_current_batch = 0
                    
                    if f_easy:
                        try:
                            f_easy.write(current_pgn_string + "\n\n")
                            easy_puzzles_in_current_batch += 1
                        except IOError as e:
                            print(f"Error writing to easy batch file {f_easy.name}: {e}")
                else:
                    board_for_san = chess.Board(fen)
                    solution_san = board_for_san.san(solution_move_object)
                    maia_san = board_for_san.san(maia_top_move)
                    print(f"  Classification for {current_puzzle_id_str}: Hard (Solution: {solution_san}, Maia's top: {maia_san})")
                    hard_puzzles_pgn_strings.append(current_pgn_string)
                    if f_hard is None or hard_puzzles_in_current_batch >= PUZZLES_PER_BATCH:
                        if f_hard:
                            f_hard.close()
                            print(f"Closed hard batch file: {f_hard.name}")
                        hard_batch_num += 1
                        current_hard_filename = f"{hard_base_name}_batch_{hard_batch_num}.pgn"
                        try:
                            f_hard = open(current_hard_filename, 'w', encoding='utf-8')
                            print(f"Opened new hard batch file: {current_hard_filename}")
                        except IOError as e:
                            print(f"Error opening hard batch file {current_hard_filename}: {e}")
                            f_hard = None # Prevent further writes if open failed
                        hard_puzzles_in_current_batch = 0
                    
                    if f_hard:
                        try:
                            f_hard.write(current_pgn_string + "\n\n")
                            hard_puzzles_in_current_batch += 1
                        except IOError as e:
                            print(f"Error writing to hard batch file {f_hard.name}: {e}")

    except FileNotFoundError:
        print(f"Error: Input PGN file not found at '{input_pgn_filepath}'")
        return 
    except Exception as e:
        print(f"An unexpected error occurred while processing the PGN file: {e}")
    finally:
        if engine:
            engine.quit()
            print("Maia engine quit.")
        if f_easy:
            f_easy.close()
            print(f"Closed final easy batch file: {f_easy.name}")
        if f_hard:
            f_hard.close()
            print(f"Closed final hard batch file: {f_hard.name}")

    # Summary of processing
    print(f"\nSummary: Processed {processed_puzzles_count} puzzles.")
    print(f"  Total Easy puzzles: {len(easy_puzzles_pgn_strings)}")
    if easy_batch_num > 0:
        print(f"  Easy puzzles written to {easy_batch_num} batch file(s) (base: {easy_base_name}_batch_N.pgn)")
    print(f"  Total Hard puzzles: {len(hard_puzzles_pgn_strings)}")
    if hard_batch_num > 0:
        print(f"  Hard puzzles written to {hard_batch_num} batch file(s) (base: {hard_base_name}_batch_N.pgn)")
    if error_puzzles_count > 0:
        print(f"  Puzzles skipped due to errors: {error_puzzles_count}")


if __name__ == "__main__":
    input_pgn_file_to_process = None
    create_sample_file = False

    if len(sys.argv) > 1:
        input_pgn_file_to_process = sys.argv[1]
        print(f"Processing user-provided PGN file: {input_pgn_file_to_process}")
    else:
        input_pgn_file_to_process = "sample_puzzles_to_classify.pgn"
        create_sample_file = True
        print(f"No input PGN file provided. Will create and process: {input_pgn_file_to_process}")

    # Define output file names (can be kept generic or derived from input)
    easy_puzzles_file = "easy_puzzles_output.pgn"
    hard_puzzles_file = "hard_puzzles_output.pgn"

    if create_sample_file:
        # Create a sample multi-PGN content string
        # Puzzle 1 (Easy if Maia finds Qd6 for the given FEN)
        # FEN: r2q3r/ppp2k2/5np1/3p4/6b1/5P2/PP2Q1PP/RNB1R2K b - - 0 1
        # Maia's top move for this position with maia-1100 is indeed Qd6.
        pgn_multi_example = """[Event "Puzzle 1 (Easy Example)"]
[Site "ClassifyTest"]
[Date "2024.01.01"]
[Round "?"]
[White "?"]
[Black "?"]
[Result "*"]
[FEN "r2q3r/ppp2k2/5np1/3p4/6b1/5P2/PP2Q1PP/RNB1R2K b - - 0 1"]
[SetUp "1"]

1... Qd6 *

"""
        # Puzzle 2 (Hard Example - Start Position, solution d4, Maia likely e4)
        # FEN: rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1
        # Maia's top move for starting position is e4.
        pgn_multi_example += """[Event "Puzzle 2 (Hard Example)"]
[Site "ClassifyTest"]
[Date "2024.01.01"]
[Round "?"]
[White "?"]
[Black "?"]
[Result "*"]
[FEN "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"]
[SetUp "1"]

1. d4 *

"""
        # Puzzle 3 (Identical to Puzzle 1, should also be Easy)
        pgn_multi_example += """[Event "Puzzle 3 (Same as 1, Easy)"]
[Site "ClassifyTest"]
[Date "2024.01.01"]
[Round "?"]
[White "?"]
[Black "?"]
[Result "*"]
[FEN "r2q3r/ppp2k2/5np1/3p4/6b1/5P2/PP2Q1PP/RNB1R2K b - - 0 1"]
[SetUp "1"]

1... Qd6 *

"""
        # Puzzle 4 (Valid Example - Sicilian Defense, Najdorf, White's 6th move)
        # FEN after 1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6
        pgn_multi_example += """[Event "Puzzle 4 (Valid Example)"]
[Site "ClassifyTest"]
[Date "2024.01.01"]
[Round "?"]
[White "?"]
[Black "?"]
[Result "*"]
[FEN "rnbqkb1r/1p2pppp/p2p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 6"]
[SetUp "1"]

6. Be3 *

"""
        # Puzzle 5 (Valid Example - Simple King and Pawn endgame)
        # FEN: 8/8/8/8/k7/P7/K7/8 w - - 0 1
        pgn_multi_example += """[Event "Puzzle 5 (Valid Example Endgame)"]
[Site "ClassifyTest"]
[Date "2024.01.01"]
[Round "?"]
[White "?"]
[Black "?"]
[Result "*"]
[FEN "8/8/8/8/k7/P7/K7/8 w - - 0 1"]
[SetUp "1"]

1. Kb2 *

"""
        # Write the sample PGN content to the input file
        try:
            with open(input_pgn_file_to_process, 'w') as f:
                f.write(pgn_multi_example)
            print(f"Sample PGN data written to {input_pgn_file_to_process}")
        except IOError as e:
            print(f"Error writing sample PGN file: {e}")
            exit()

    process_pgn_file(input_pgn_file_to_process, easy_puzzles_file, hard_puzzles_file)

    if create_sample_file:
        print(f"\nTo clean up test files generated by this run, you can delete: {input_pgn_file_to_process}, and batch files starting with '{easy_puzzles_file.rsplit('.',1)[0]}_batch_' and '{hard_puzzles_file.rsplit('.',1)[0]}_batch_'.")
    else:
        print(f"\nOutput batch files start with prefixes: '{easy_puzzles_file.rsplit('.',1)[0]}_batch_' and '{hard_puzzles_file.rsplit('.',1)[0]}_batch_'.")
