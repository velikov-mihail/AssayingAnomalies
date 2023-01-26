function ppi = csppind(x,a,b,n,ck)
% CSPPIND Chi-square projection pursuit index.
%   
%   PPI = CSPPIND(Z,ALPHA,BETA,N,CK)
%   This finds the value of the projection pursuit index
%   for a plane spanned by the column vectors ALPHA and
%   BETA. The vector CK contains the bivariate standard
%   normal probabilities for radial boxes. CK is usually
%   found in the function CSPPEDA. The matrix Z is the
%   sphered or standardized version of the data.
%
%   See also CSPPEDA, CSPPSTRTREM

%   W. L. and A. R. Martinez, 9/15/01
%   Computational Statistics Toolbox 




z=zeros(n,2);
ppi=0;
pk=zeros(1,48);
eta = pi*(0:8)/36;
delang=45*pi/180;
delr=sqrt(2*log(6))/5;
angles=0:delang:(2*pi);
rd = 0:delr:5*delr;
nr=length(rd);
na=length(angles);

for j=1:9
   % find rotated plane
   aj=a*cos(eta(j))-b*sin(eta(j));
   bj=a*sin(eta(j))+b*cos(eta(j));
   % project data onto this plane
   z(:,1)=x*aj;
   z(:,2)=x*bj;
   % convert to polar coordinates
   [th,r]=cart2pol(z(:,1),z(:,2));
   % find all of the angles that are negative
	ind = find(th<0);
	th(ind)=th(ind)+2*pi;
   % find # points in each box
   for i=1:(nr-1)	% loop over each ring
      for k=1:(na-1)	% loop over each wedge
         ind = find(r>rd(i) & r<rd(i+1) & th>angles(k) & th<angles(k+1));
         pk((i-1)*8+k)=(length(ind)/n-ck((i-1)*8+k))^2/ck((i-1)*8+k);
      end
   end
   % find the number in the outer line of boxes
   for k=1:(na-1)
      ind=find(r>rd(nr) & th>angles(k) & th<angles(k+1));
      pk(40+k)=(length(ind)/n-(1/48))^2/(1/48);
   end
   ppi=ppi+sum(pk);
end
ppi=ppi/9;