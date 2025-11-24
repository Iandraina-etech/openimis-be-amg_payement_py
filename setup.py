import os
from setuptools import find_packages, setup

with open(os.path.join(os.path.dirname(__file__), 'README.md')) as readme:
    README = readme.read()

os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='openimis-be-amg_payement',
    version='1.3.0',
    packages=find_packages(),
    include_package_data=True,
    package_data={
        'amg_payement': [
            'templates/payments/*.html',
            'templates/payments/**/*.html',
            'static/payments/css/*.css',
            'static/payments/js/*.js',
            'static/payments/images/*',
            'static/payments/**/*',
        ],
    },
    license='GNU AGPL v3',
    description='The openIMIS Backend Comores payement module.',
    long_description=README,
    long_description_content_type='text/markdown',
    url='https://openimis.org/',
    author='',
    author_email='',
    install_requires=[
        'django>=4.2,<5.0',
        'django-db-signals',
        'djangorestframework',
        # Ajoutez les dépendances de holo_site/requirements.txt
    ],
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Framework :: Django :: 4.2',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Affero General Public License v3',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
    ],
)