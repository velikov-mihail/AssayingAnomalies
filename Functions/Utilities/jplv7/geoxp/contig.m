function W=contig(x,y,distance)
% PURPOSE : This function computes a contiguity matrix based on a distance threshold
%---------------------------------------------------------------------------
% USAGE : W=contig(x,y,distance)
%    where : x : (n x 1) vector of the latitudes
%            y : (n x 1) vector of the longitudes
%            distance : threshold distance  
%----------------------------------------------------------------------------- 
% OUTPUTS :  W : contiguity matrix(n x n) 
%-----------------------------------------------------------------------------   
% used in morancontiplot.m
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr



W=zeros(length(x),length(x));

%W=normw(W);% normalize the matrix

Tp1=repmat(x',length(x),1);
Tp2=repmat(y',length(y),1);
H=sqrt((repmat(x,1,length(x))-Tp1).^2+(repmat(y,1,length(y))-Tp2).^2);
W(find(H<=distance))=1;
W=W-eye(length(x));