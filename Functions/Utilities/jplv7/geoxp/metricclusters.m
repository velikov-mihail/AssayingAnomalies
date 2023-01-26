function [out]=metricclusters(data,beta)
% PURPOSE : computes a data-based metric adapted to the detection of clusters
%---------------------------------------------------------------------------
% USAGE : [out]=metricclusters(data,beta)
%    where : data = (n x p) data matrix
%            beta = strictly positive parameter (the default is beta=0.05)
%----------------------------------------------------------------------------- 
% OUTPUTS :  out = p x p matrix (metric)
%-----------------------------------------------------------------------------
% Anne Ruiz-Gazen, Julien Moutel, June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr


if nargin<2
    beta=0.05;
end;
x=data;
[n,p]=size(x);
xbar=sum(repmat(1/n*ones(n,1),1,p).*x)';
xc=x-ones(n,1)*xbar';
cov=(xc'*xc)/n;
invcov=inv(cov);
num=0;
den=0;
for i=1:n
    for j=i:n
        xij=(x(i,:)-x(j,:))';
        wij=exp((-beta/2)*xij'*invcov*xij);
        num=num+wij*xij*xij';
        den=den+wij;
    end;
end;
cluster_cov=num/den;
out=inv(cluster_cov);