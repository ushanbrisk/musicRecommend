1.各个脚本解释如下：

init_music_feature_api.py
调用云厂商的api， 抽取特征， 但是很慢，  大概0.03 songs/second, 

init_music_feature_vllm.py
第一版本的本地架设大模型抽取， 需要前提， 就是start_vllm_servers.sh启动
一般是先 bash scripts/start_vllm_servers.sh start( all?) 启动服务器， 这里是架设了2个大模型
然后python scripts/init_music_feature_vllm.py ， 抽取


第二版本：
改为单模型
启动服务  bash scripts/start_vllm_servers_v2.sh
抽取      python scripts/init_music_feature_vllm_v2.py
从短到长， 可能batch_size需要再调一下， 速度也慢

第三版本:
bash scripts/start_vllm_servers_v3.sh
python scripts/init_music_feature_vllm_v3.py

第二版本是最终定型的版本， 单模型； 但是还是不行 太慢



init_song_comment_agg.py
init_song_playlist_agg.py这2个文件是用来生成中间用到的聚合表的sql

sync_database.py 是把本机musicdb数据库内容同步到远程192.168.3.3的脚本

compare_features.py 这是用来比较不同模型， 比如14b, 32b抽取的特征的相似度



最好， 意识到一点， 离线用大模型处理所有的几十万首歌曲， 是mission impossible

