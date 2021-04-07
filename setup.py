#
#   Copyright 2020 Logical Clocks AB
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#

import os
from setuptools import setup, find_packages
from maggy.version import __version__


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name='maggy',
    version=__version__,
    install_requires=[
        'numpy', 'scikit-optimize==0.7.4', 'statsmodels==0.11.0', 'scipy==1.4.1'
    ],
    extras_require={
        'pydoop': ['pydoop'],
        'tf': ['tensorflow==2.4.1'],
        'torch': ['torch==1.7.1'],  # Should be 1.8.1 if we want to support PyTorch's ZeRO.
        'zero': ['deepspeed==0.3.13',
                 'fairscale==0.3.0'],
        'docs': [
            'sphinx==1.8.5',
            'sphinx-autobuild',
            'recommonmark',
            'sphinx_rtd_theme',
            'jupyter_sphinx_theme'
        ],
        'test': [
            'pylint',
            'pytest',
        ],
        'dev': [
            'black',
            'flake8',
        ],
        'spark': ['pyspark==2.4.3']
    },
    author='Moritz Meister',
    author_email='meister.mo@gmail.com',
    description='Efficient asynchronous optimization of expensive black-box functions on top of Apache Spark',
    license='GNU Affero General Public License v3',
    keywords='Hyperparameter, Optimization, Auto-ML, Hops, Hadoop, TensorFlow, Spark',
    url='https://github.com/logicalclocks/maggy',
    download_url='http://snurran.sics.se/hops/maggy/maggy-' + __version__ + '.tar.gz',
    packages=find_packages(),
    long_description=read('README.rst'),
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Topic :: Utilities',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3',
    ]
)
