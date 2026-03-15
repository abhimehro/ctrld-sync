mkdir -p codacy_run_test
cd codacy_run_test
cp -r ../.git .
cp -r ../tests .
cp ../main.py .
cp ../.codacy.yml .
find . -type f -exec file {} \; | grep -v -i "ASCII"
