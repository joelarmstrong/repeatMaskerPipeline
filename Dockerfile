FROM debian:stretch AS builder
RUN apt-get update
RUN apt-get install -y perl wget patch build-essential cpio
# RepeatMasker
RUN wget http://www.repeatmasker.org/RepeatMasker-open-4-0-7.tar.gz
RUN tar xzvf RepeatMasker-open-4-0-7.tar.gz
RUN rm RepeatMasker-open-4-0-7.tar.gz
# RMBlast
RUN wget ftp://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/2.6.0/ncbi-blast-2.6.0+-src.tar.gz
RUN wget http://www.repeatmasker.org/isb-2.6.0+-changes-vers2.patch.gz
RUN tar xzvf ncbi-blast-2.6.0+-src.tar.gz
RUN gunzip isb-2.6.0+-changes-vers2.patch.gz
WORKDIR ncbi-blast-2.6.0+-src
RUN patch -p1 < ../isb-2.6.0+-changes-vers2.patch
WORKDIR c++
RUN ./configure --with-mt --prefix=/usr/local/rmblast --without-debug
RUN make
RUN make install || echo "ignoring expected error"
WORKDIR /
RUN rm isb-2.6.0+-changes-vers2.patch
RUN rm ncbi-blast-2.6.0+-src.tar.gz
# TRF
RUN wget https://tandem.bu.edu/trf/downloads/trf409.linux64 -o /bin/trf
RUN chmod +x /bin/trf
# Kent utils
RUN wget http://hgdownload.soe.ucsc.edu/admin/exe/linux.x86_64/faSplit -O /bin/faSplit
RUN chmod +x /bin/faSplit
RUN wget http://hgdownload.soe.ucsc.edu/admin/exe/linux.x86_64/liftUp -O /bin/liftUp
RUN chmod +x /bin/liftUp
RUN wget http://hgdownload.soe.ucsc.edu/admin/exe/linux.x86_64/faToTwoBit -O /bin/faToTwoBit
RUN chmod +x /bin/faToTwoBit
RUN wget http://hgdownload.soe.ucsc.edu/admin/exe/linux.x86_64/twoBitMask -O /bin/twoBitMask
RUN chmod +x /bin/twoBitMask
RUN wget http://hgdownload.soe.ucsc.edu/admin/exe/linux.x86_64/twoBitToFa -O /bin/twoBitToFa
RUN chmod +x /bin/twoBitToFa

RUN apt-get install -y cpanminus
RUN cpanm Text::Soundex
# Copy any libraries from the user
COPY Libraries/* /RepeatMasker/Libraries/
# Configuration
WORKDIR /RepeatMasker
COPY RepeatMaskerConfig.pm /RepeatMasker/
RUN echo '\n\n\n/bin/trf\n2\n/usr/local/rmblast\n\n5\n' | perl ./configure

# Create a thinner final Docker image (the previous steps add ~2GB in useless layers)
FROM debian:stretch
COPY --from=builder /bin/trf /bin/faSplit /bin/liftUp /bin/twoBitToFa /bin/faToTwoBit /bin/twoBitMask /bin/
COPY --from=builder /RepeatMasker /RepeatMasker
# Copy RMBlast
COPY --from=builder /usr/local/rmblast /usr/local/rmblast
# Copy any engines from the user
COPY engines/* /usr/local/bin/
# Install runtime dependencies
RUN apt-get update && apt-get install -y libkrb5-3 libgomp1 perl
COPY --from=builder /usr/local/lib/x86_64-linux-gnu/perl/ /usr/local/lib/x86_64-linux-gnu/perl/
ENV PATH="/RepeatMasker:${PATH}"