FROM fedora:latest
RUN echo "Secret123" | passwd --stdin root
RUN dnf install -y systemd openssh-server && dnf clean all
RUN echo "PermitRootLogin yes" >> /etc/ssh/sshd_config
RUN systemctl enable sshd

RUN dnf install -y 389-ds-base && dnf clean all
COPY ./instance.inf /root/localhost.inf
COPY ./allow_anon.ldif /root/allow_anon.ldif
COPY ./allow_anon.service /etc/systemd/system/allow_anon.service
RUN sed -i 's/with_systemd = 1/with_systemd = 0/g' /usr/share/dirsrv/inf/defaults.inf
RUN dscreate from-file /root/localhost.inf
RUN sed -i 's/with_systemd = 0/with_systemd = 1/g' /usr/share/dirsrv/inf/defaults.inf
RUN systemctl enable dirsrv@localhost
RUN systemctl enable allow_anon.service

CMD ["/sbin/init"]
STOPSIGNAL SIGRTMIN+3
