scripts/init_song_embeddings.py已经实现。但是api的问题是时常断掉，封掉。我现在想实现一个并列的方案，不妨把原来的api方案叫做planA,planB就是本地GPU部署模型，本地有3张3090 24g， 3张3080 20g, 可以并行跑，可以通过song_id%6的余数来分组。我希望你帮我实现这个方案，注意，这个方案必须精简，完美替换scripts/init_song_embeddings.py。 具体一点，就是文本构造不变，之前是调用        response = embedding_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
            encoding_format="float"
        )， 现在改成用本地模型， 但是我希望输出的结果，格式，内容都是和api方案有一致性的。另外，注明了需要安装哪些包，在requirements.txt中添加。先完成设计文档的改动，然后实现代码。
