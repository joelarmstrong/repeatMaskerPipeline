FROM debian:stretch
RUN ["apt-get", "update"]
RUN ["apt-get", "install", "-y", "perl", "wget", "patch", "build-essential", "cpio"]
# RepeatMasker
RUN ["wget", "http://www.repeatmasker.org/RepeatMasker-open-4-0-7.tar.gz"]
RUN ["tar", "xzvf", "RepeatMasker-open-4-0-7.tar.gz"]
# RMBlast
RUN ["wget", "ftp://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/2.6.0/ncbi-blast-2.6.0+-src.tar.gz"]
RUN ["wget", "http://www.repeatmasker.org/isb-2.6.0+-changes-vers2.patch.gz"]
RUN ["tar", "xzvf", "ncbi-blast-2.6.0+-src.tar.gz"]
RUN ["gunzip", "isb-2.6.0+-changes-vers2.patch.gz"]
WORKDIR ncbi-blast-2.6.0+-src
RUN patch -p1 < ../isb-2.6.0+-changes-vers2.patch
WORKDIR c++
RUN ["./configure", "--with-mt", "--prefix=/usr/local/rmblast", "--without-debug"]
RUN ["make"]
RUN make install || echo "ignoring expected error"# Copy any libraries from the user
COPY Libraries/* /RepeatMasker/Libraries/
# Configuration
COPY RepeatMaskerConfig.pm /RepeatMasker/
WORKDIR /RepeatMasker
