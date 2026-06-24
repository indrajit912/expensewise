from setuptools import setup, find_packages

setup(
    name='expensewise-cli',
    version='0.1.0',
    author='Indrajit Ghosh',
    url='https://github.com/indrajit912',
    packages=find_packages(),
    install_requires=[
        'click>=8.0.0',
        'requests>=2.25.0',
        'rich>=13.0.0',
    ],
    entry_points={
        'console_scripts': [
            'expense-cli=cli.main:cli',
        ],
    },
)
