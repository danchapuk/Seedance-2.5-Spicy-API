from setuptools import setup

setup(
    name="seedance-2-5-spicy-api",
    version="0.2.0",
    author="Anil Matcha",
    description="Python wrapper & Web Studio for ByteDance's Seedance 2.5 Spicy API — supporting BytePlus ModelArk, fal.ai, WaveSpeedAI, Replicate, and MuAPI. Native 4K, 30s clips, native audio, Omni Reference, Video Edit/Extend, and Motion Control.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    py_modules=["seedance_2_5_spicy_api", "mcp_server", "server"],
    package_data={"": ["static/*"]},
    include_package_data=True,
    install_requires=[
        "requests",
        "python-dotenv",
        "mcp[cli]"
    ],
    extras_require={
        "studio": [
            "fastapi>=0.100.0",
            "uvicorn[standard]>=0.22.0",
            "python-multipart>=0.0.6",
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
)
