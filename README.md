# Just-Feed
A microservice application for the CICD2 project

## Project Setup

### Setting up a python virtual environment

````bash
python -m venv venv
````

Activate using:

````bash
source venv/Scripts/activate
````

### Installing dependancies

````bash
make install
````

Run the following commdand when adding new libraries

````bash
make freeze
````

### Starting application

The start/run commands are formatted as "make start/run"

````bash
make run
````

````bash
make start
````

````bash
make stop
````
### Running tests

````bash
make test
````