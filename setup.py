from setuptools import setup, find_packages

setup(
    name='dabry',
    version='1.0.1',
    description='Trajectory optimization in flow fields',
    author='Bastien Schnitzler',
    author_email='bastien.schnitzler@live.fr',
    packages=find_packages('src'),  # same as name
    package_dir={'': 'src'},
    install_requires=['alphashape',
                      'ambiance',
                      'basemap',
                      'cdsapi',
                      'geopy',
                      'h5py',
                      'Markdown',
                      'matplotlib',
                      'numpy',
                      'pygrib',
                      'pyproj',
                      'scipy',
                      'Shapely',
                      'tqdm'],
)
