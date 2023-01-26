function s=kern_den(ech,band,eval)
% PURPOSE : Kernel estimator of the density (of Parzen-Rosenblatt)
% for a unidimensional sample 
%--------------------------------------------------------------
% USAGE: s=kern_de1(ech,band,eval)
% where:   ech =  sample (vector nx1)
%          band = band (scalar)
%          eval = points where the density is evaluated (vector px1)
%--------------------------------------------------------------
% OUTPUTS: s = values of the estimator of the density at the points in eval (vector px1)
%--------------------------------------------------------------
% NOTE: uses the kernel given by the function noy.m
%--------------------------------------------------------------
% Christine Thomas-Agnan, June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr



ss=zeros(length(ech),length(eval));

for i=1:length(ech)

ss(i,:)=noy((eval-ech(i)*ones(1,length(eval)))./band)./band;

end

s=mean(ss);

