function r = kern_re(ech_abs,ech_ord,band,eval)
% PURPOSE: Kernel estimator of regression (of Nadaraya-Watson)
% for a bidimensional sample (ech_abs,ech_ord)
%--------------------------------------------------------------
% USAGE: r = kern_re(ech_abs,ech_ord,band,eval)
% where:   ech_abs =  first coordinates of the points of the sample (vector 1xn)
%          ech_ord =  second coordinates of the points of the sample (vector 1xn)
%          band = band (scalar)
%          eval = coordinates on the first axis where the density is evaluated (vector 1xp)
%--------------------------------------------------------------
% OUTPUTS: r = values of the estimator of regression at the points whose first coordinatea are in eval (vector 1*p)
%--------------------------------------------------------------
% NOTE: uses the kernel given by the function noy.m
%--------------------------------------------------------------
%--------------------------------------------------------------
% Christine Thomas-Agnan, June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr



num=zeros(1,length(eval));
den=zeros(1,length(eval));
for i=1:length(ech_abs)
tem=noy((eval-ech_abs(i)*ones(1,length(eval)))/band);
num=num+ech_ord(i).*tem;
den=den+tem;
end
for j=1:length(eval)
if den(j) ~=0
r(j)=num(j)/den(j);
else
r(j)=mean(ech_ord);
end
end
