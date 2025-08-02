import re

ja ='mube,mube抱啊实打实打算撒打算'

print(re.sub('mube', 'むべ', ja, re.DOTALL))