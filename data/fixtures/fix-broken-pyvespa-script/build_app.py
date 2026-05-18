"""Build a pyvespa application package and write it to disk.

There are several bugs in this script. Find and fix them all.
"""

from vespa.package import (
    HNSW,
    ApplicationPackage,
    Field,
    FieldSet,
    RankProfile,
)


def build_app():
    # App name uses a hyphen which is not allowed by pyvespa's name rules.
    app = ApplicationPackage(name="my-search-app")

    app.schema.add_fields(
        Field(
            name="title",
            type="string",
            indexing=["index", "summary"],
            index="enable-bm25",
        ),
        Field(
            name="body",
            type="string",
            indexing=["index", "summary"],
            index="enable-bm25",
        ),
        Field(
            name="category",
            type="string",
            indexing=["attribute", "summary"],
            attribute="fast-search",
        ),
        Field(
            name="embedding",
            type="tensor<float>(x[384])",
            indexing=["input title | embed e5 | index | attribute"],
            ann=HNSW(distance_metric="angular"),
        ),
    )

    app.schema.add_field_set(FieldSet(name="default", fields=["title", "body"]))

    app.schema.add_rank_profile(
        RankProfile(
            name="hybrid",
            inputs=[("query(q)", "tensor<float>(x[384])")],
            first_phase="bm25(title) + bm25(body) + closeness(field, embedding)",
        )
    )

    return app


if __name__ == "__main__":
    app = build_app()
    app.to_files("./output")
    print("done — wrote to ./output")
