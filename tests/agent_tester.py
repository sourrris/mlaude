import pexpect
import sys
import time

def run_tests():
    print("Starting mlaude CLI tester (Phase 4 - Subcommands)...")
    
    # Test `mlaude serve`
    print("\n--- Testing `mlaude serve` ---")
    child = pexpect.spawn('uv run mlaude serve --port 8484', encoding='utf-8', dimensions=(24, 200))
    child.logfile_read = sys.stdout
    try:
        child.expect(r'Listening: http://0.0.0.0:8484', timeout=5)
        print("\n\n--- `mlaude serve` started successfully ---")
        time.sleep(2)
        child.sendintr() # Ctrl+C to stop
        child.expect(pexpect.EOF, timeout=5)
        print("\n--- `mlaude serve` stopped gracefully ---")
    except Exception as e:
        print(f"\n--- `mlaude serve` FAILED: {e} ---")
        print(child.before)
    finally:
        child.close()

    # Test `mlaude gateway`
    print("\n--- Testing `mlaude gateway` ---")
    child = pexpect.spawn('uv run mlaude gateway --port 8585', encoding='utf-8', dimensions=(24, 200))
    child.logfile_read = sys.stdout
    try:
        child.expect(r'Listening: http://0.0.0.0:8585', timeout=5)
        print("\n\n--- `mlaude gateway` started successfully ---")
        time.sleep(2)
        child.sendintr()
        child.expect(pexpect.EOF, timeout=5)
        print("\n--- `mlaude gateway` stopped gracefully ---")
    except Exception as e:
        print(f"\n--- `mlaude gateway` FAILED: {e} ---")
        print(child.before)
    finally:
        child.close()

if __name__ == '__main__':
    run_tests()
