import sys 
import re

match_spaces = re.compile('^(\s*)')

with sys.stdin as f:
    buffer = [line for line in f]

match = match_spaces.match(buffer[0])
leading_spaces = match.groups()[0]
leading_len = len(leading_spaces)

new_buffer = ''.join([line[leading_len:] for line in buffer])
print(new_buffer)
