from setuptools import setup, find_packages
from pathlib import Path

this_directory = Path(__file__).parent

# Lee requirements.txt desde el directorio actual de setup.py
requirements_path = this_directory / 'requirements.txt'
with open(requirements_path, encoding='utf-8') as f:
    required_packages = f.read().splitlines()

# Lee README.md para el long_description
readme_path = this_directory / 'README.md'
with open(readme_path, encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='panzer',
    version='1.0.11',
    author='nand0san',
    author_email='',
    description='REST API manager for Binance API. Manages weights and credentials simply and securely.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/nand0san/panzer',
    packages=find_packages(),
    include_package_data=True,  # Asegura que se respete MANIFEST.in
    install_requires=required_packages,

    classifiers=[
        'Development Status :: 3 - Alpha',  # 3 - Alpha/4 - Beta/5 - Production/Stable
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.11',  # Especifica las versiones que soporta
        # 'Programming Language :: Python :: 3.9',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.11',  # Especifica la versión de Python necesaria
    package_data={
        # Si hay datos como .json o .txt que necesitas incluir, especifica aquí
    },
    exclude_package_data={'': ['*.ipynb', '*.ipynb_checkpoints/*']},  # Exclusión de notebooks y checkpoints
)
