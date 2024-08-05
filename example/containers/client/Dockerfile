FROM fedora:latest
RUN echo "Secret123" | passwd --stdin root
RUN dnf install -y systemd openssh-server && dnf clean all
RUN echo "PermitRootLogin yes" >> /etc/ssh/sshd_config
RUN systemctl enable sshd

RUN dnf install -y sudo sssd shadow-utils && dnf clean all
RUN systemctl disable sssd

CMD ["/sbin/init"]
STOPSIGNAL SIGRTMIN+3
